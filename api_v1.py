"""Marketplace JSON API under /api/v1. Off unless MARKETPLACE_ENABLED=1.

Mixin for AdenCleanHandler: uses its read_json, send_json, enforce_rate_limit, store and
admin-session helpers. Every response is JSON; errors never reveal whether an account exists.
"""

import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from api_v1_payments import PAYMENT_ROUTES, PaymentRoutes
from api_v1_vetting import VETTING_ROUTES, VettingRoutes, vetting_required
from marketplace import accounts, bookings, jobs, locks, mailer, offers
from marketplace import config as mconfig
from marketplace.storage import MarketplaceStore, tables_for
from store import Conflict, NotFound, StoreError
from validation import ApiError, clean_email, clean_text

SERVICE_TYPES = {"regular", "deep", "move-in-move-out", "post-party"}
SUPPLIES = {"customer", "cleaner"}
_MARKET_LOCK = threading.Lock()  # guards creating the per-store MarketplaceStore


def enabled():
    return os.environ.get("MARKETPLACE_ENABLED", "") == "1"


def _now():
    return datetime.now(timezone.utc)


def _int(value, label, low, high, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ApiError(400, f"{label} must be a whole number from {low} to {high}.")
    return value


def _date(value, label):
    try:
        return date.fromisoformat(clean_text(value, label, 10))
    except ValueError as error:
        raise ApiError(400, f"Choose a valid {label.lower()}.") from error


def _offer_from_row(row):
    return offers.Offer(id=row["id"], job_id=row["job_id"], cleaner_id=row["cleaner_id"],
                        price_cents=row["price_cents"], status=row["status"],
                        counter_rounds=row["counter_rounds"], awaiting=row["awaiting"])


def _expired(row, now):
    return datetime.fromisoformat(row["expires_at"]) <= now


ROUTES = [  # (method, pattern, handler name)
    ("POST", r"/api/v1/auth/request-code", "v1_request_code"),
    ("POST", r"/api/v1/auth/verify-code", "v1_verify_code"),
    ("POST", r"/api/v1/auth/delete-account", "v1_delete_account"),
    ("GET", r"/api/v1/me", "v1_me"),
    ("POST", r"/api/v1/jobs", "v1_create_job"),
    ("GET", r"/api/v1/jobs/mine", "v1_my_jobs"),
    ("GET", r"/api/v1/jobs/open", "v1_open_jobs"),
    ("GET", r"/api/v1/jobs/(?P<job_id>[0-9a-f]{32})", "v1_get_job"),
    ("POST", r"/api/v1/jobs/(?P<job_id>[0-9a-f]{32})/cancel", "v1_cancel_job"),
    ("GET", r"/api/v1/jobs/(?P<job_id>[0-9a-f]{32})/offers", "v1_job_offers"),
    ("POST", r"/api/v1/jobs/(?P<job_id>[0-9a-f]{32})/offers", "v1_create_offer"),
    ("POST", r"/api/v1/offers/(?P<offer_id>[0-9a-f]{32})/(?P<action>counter|accept|decline|withdraw)",
     "v1_offer_action"),
    ("POST", r"/api/v1/admin/cleaners", "v1_admin_set_cleaner"),
]


class MarketplaceRoutes(PaymentRoutes, VettingRoutes):
    # -- plumbing --------------------------------------------------------------

    @property
    def market(self):
        cached = getattr(self.store, "_marketplace", None)
        if cached is None:
            with _MARKET_LOCK:
                cached = getattr(self.store, "_marketplace", None)
                if cached is None:
                    cached = MarketplaceStore(tables_for(self.store))
                    self.store._marketplace = cached
        return cached

    @property
    def mconf(self):
        return mconfig.load()

    def handle_v1(self, method):
        path = urlsplit(self.path).path
        if not enabled():
            self.send_json(404, {"ok": False, "error": "That endpoint was not found."})
            return
        for route_method, pattern, name in ROUTES + PAYMENT_ROUTES + VETTING_ROUTES:
            match = re.fullmatch(pattern, path)
            if match and route_method == method:
                try:
                    getattr(self, name)(**match.groupdict())
                except accounts.AuthError as error:
                    self.send_json(error.status, {"ok": False, "error": error.message})
                except ApiError as error:
                    self.send_json(error.status, {"ok": False, "error": error.message})
                except (offers.OfferError, jobs.TransitionError) as error:
                    self.send_json(409, {"ok": False, "error": str(error)})
                except NotFound:
                    self.send_json(404, {"ok": False, "error": "That was not found."})
                except Conflict:
                    self.send_json(409, {"ok": False, "error": "That already exists."})
                except StoreError:
                    self.send_storage_error("Something went wrong. Please try again.")
                return
        self.send_json(404, {"ok": False, "error": "That endpoint was not found."})

    def _secret(self):
        secret = os.environ.get("SESSION_SECRET", "")
        if len(secret) < 32:
            raise ApiError(503, "Sign-in is not available right now.")
        return secret

    def current_user(self):
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        user_id = accounts.read_token(self._secret(), token)
        if not user_id:
            raise ApiError(401, "Sign in to continue.")
        try:
            user = self.market.get_user(user_id)
        except NotFound:
            raise ApiError(401, "Sign in to continue.") from None
        if user["status"] != "active":
            raise ApiError(401, "Sign in to continue.")
        self.enforce_rate_limit(bucket="v1:" + user_id, limit=300,
                                message="Too many requests. Please wait a moment.")
        return user

    def _require_cleaner(self, user):
        if "cleaner" not in accounts.roles_of(user):
            raise ApiError(403, "Only activated cleaners can do this.")

    # -- auth ------------------------------------------------------------------

    def v1_request_code(self):
        self.enforce_rate_limit(bucket="v1-code", limit=10)
        email = clean_email(self.read_json().get("email"))
        try:
            code = accounts.issue_code(self.market, self._secret(), email)
            mailer.send_code(email, code)
        except mailer.MailError as error:
            raise ApiError(503, str(error)) from error
        except accounts.AuthError as error:
            if error.status != 429:
                raise
        # Same answer whether or not the email has an account.
        self.send_json(200, {"ok": True, "message": "If that email can sign in, a code is on its way."})

    def v1_verify_code(self):
        self.enforce_rate_limit(bucket="v1-verify", limit=20)
        payload = self.read_json()
        email = clean_email(payload.get("email"))
        accounts.check_code(self.market, self._secret(), email, payload.get("code"))
        name = clean_text(payload.get("displayName") or email.split("@")[0], "Name", 80)
        ip = self.client_address[0]
        user, created = accounts.sign_in(self.market, email, name, payload.get("acceptTerms"), ip)
        token = accounts.make_token(self._secret(), user["id"])
        self.send_json(200, {"ok": True, "token": token, "created": created, "user": self._me(user)})

    @staticmethod
    def _me(user):
        return {"id": user["id"], "email": user["email"], "displayName": user["display_name"],
                "roles": sorted(accounts.roles_of(user))}

    def v1_me(self):
        self.send_json(200, {"ok": True, "user": self._me(self.current_user())})

    def v1_delete_account(self):
        user = self.current_user()
        payload = self.read_json()
        if payload.get("confirm") != "DELETE":
            raise ApiError(400, 'Type DELETE to confirm.')
        with locks.BOOKING_LOCK:
            cancelled = accounts.delete_account(self.market, user)
        self.send_json(200, {"ok": True, "cancelledJobs": cancelled})

    # -- jobs ------------------------------------------------------------------

    def v1_create_job(self):
        user = self.current_user()
        p, cfg, now = self.read_json(), self.mconf, _now()
        service = clean_text(p.get("serviceType"), "Service type", 40).lower()
        if service not in SERVICE_TYPES:
            raise ApiError(400, "Choose a listed service type.")
        zip_code = clean_text(p.get("zip"), "ZIP code", 10)
        if zip_code not in cfg.service_zips:
            raise ApiError(400, "AdenClean does not serve that ZIP code yet.")
        supplies = clean_text(p.get("supplies"), "Supplies", 20).lower()
        if supplies not in SUPPLIES:
            raise ApiError(400, "Say who brings the supplies.")
        date_from, date_to = _date(p.get("dateFrom"), "Start date"), _date(p.get("dateTo"), "End date")
        if date_from < now.date() or date_to < date_from or date_to > date_from + timedelta(days=30):
            raise ApiError(400, "Choose dates from today, at most 30 days apart.")
        job = {
            "id": uuid.uuid4().hex, "customer_id": user["id"], "status": "open",
            "service_type": service, "zip": zip_code,
            "bedrooms": _int(p.get("bedrooms"), "Bedrooms", 0, 10),
            "bathrooms": _int(p.get("bathrooms"), "Bathrooms", 1, 10),
            "supplies": supplies, "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
            "budget_cents": _int(p.get("budgetCents"), "Budget", cfg.min_price_cents,
                                 cfg.max_price_cents, required=False),
            "notes": clean_text(p.get("notes", ""), "Notes", 800, required=False, allow_newlines=True) or None,
            "booked_offer_id": None, "price_cents": None, "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=cfg.job_expiry_hours)).isoformat(),
            "status_updated_at": now.isoformat(),
        }
        self.market.create_job(job)
        self.send_json(201, {"ok": True, "job": self._job_view(job, owner=True)})

    @staticmethod
    def _job_view(job, owner):
        keys = ["id", "status", "service_type", "zip", "bedrooms", "bathrooms", "supplies",
                "date_from", "date_to", "budget_cents", "notes", "created_at", "expires_at"]
        if owner:
            keys += ["booked_offer_id", "price_cents"]
        return {k: job.get(k) for k in keys}

    def _expire_if_due(self, job, now):
        if job["status"] == "open" and _expired(job, now):
            job["status"] = jobs.transition("open", "expired", jobs.SYSTEM)
            self.market.update_job(job["id"], {"status": "expired", "status_updated_at": now.isoformat()})
        return job

    def v1_my_jobs(self):
        user, now = self.current_user(), _now()
        rows = [self._expire_if_due(j, now) for j in self.market.jobs_for_customer(user["id"])]
        self.send_json(200, {"ok": True, "jobs": [self._job_view(j, owner=True) for j in rows]})

    def v1_open_jobs(self):
        user, now = self.current_user(), _now()
        self._require_cleaner(user)
        rows = [self._expire_if_due(j, now) for j in self.market.open_jobs_in(self.mconf.service_zips)]
        visible = [j for j in rows if j["status"] == "open" and j["customer_id"] != user["id"]]
        self.send_json(200, {"ok": True, "jobs": [self._job_view(j, owner=False) for j in visible]})

    def v1_get_job(self, job_id):
        user, now = self.current_user(), _now()
        job = self._expire_if_due(self.market.get_job(job_id), now)
        if job["customer_id"] == user["id"]:
            self.send_json(200, {"ok": True, "job": self._job_view(job, owner=True), "role": "customer"})
            return
        self._require_cleaner(user)
        mine = [o for o in self.market.offers_for_job(job_id) if o["cleaner_id"] == user["id"]]
        if job["status"] != "open" and not mine:
            raise NotFound("job")
        self.send_json(200, {"ok": True, "job": self._job_view(job, owner=False), "role": "cleaner",
                             "myOffer": self._offer_view(mine[0], False) if mine else None})

    def v1_cancel_job(self, job_id):
        user, now = self.current_user(), _now()
        if self.market.get_job(job_id)["status"] != "open" and self.market.booking_for_job(job_id):
            return self.v1_cancel_booking(job_id)  # refunds and late fees apply
        with locks.BOOKING_LOCK:
            job = self.market.get_job(job_id)
            if job["customer_id"] != user["id"]:
                raise NotFound("job")
            jobs.transition(job["status"], "cancelled", jobs.CUSTOMER)
            self.market.update_job(job_id, {"status": "cancelled", "status_updated_at": now.isoformat()})
            self._close_other_offers(job_id, keep=None, now=now)
        self.send_json(200, {"ok": True})

    # -- offers ----------------------------------------------------------------

    def _offer_view(self, row, include_cleaner):
        view = {k: row[k] for k in ("id", "job_id", "price_cents", "status", "counter_rounds",
                                    "awaiting", "message", "created_at", "expires_at")}
        if include_cleaner:
            try:
                view["cleaner_name"] = self.market.get_user(row["cleaner_id"])["display_name"]
            except NotFound:
                view["cleaner_name"] = "Cleaner"
        return view

    def v1_job_offers(self, job_id):
        user = self.current_user()
        job = self.market.get_job(job_id)
        rows = self.market.offers_for_job(job_id)
        if job["customer_id"] == user["id"]:
            views = [self._offer_view(r, True) for r in rows]
        else:
            views = [self._offer_view(r, False) for r in rows if r["cleaner_id"] == user["id"]]
        self.send_json(200, {"ok": True, "offers": views})

    def v1_create_offer(self, job_id):
        user, cfg, now = self.current_user(), self.mconf, _now()
        self._require_cleaner(user)
        p = self.read_json()
        job = self._expire_if_due(self.market.get_job(job_id), now)
        self.require_payouts_ready(user)
        offer, flags = offers.make_offer(uuid.uuid4().hex, job, user["id"], p.get("priceCents"), cfg)
        row = {
            "id": offer.id, "job_id": job_id, "cleaner_id": user["id"], "price_cents": offer.price_cents,
            "status": offer.status, "counter_rounds": 0, "awaiting": offer.awaiting,
            "message": clean_text(p.get("message", ""), "Message", 500, required=False) or None,
            "flags": ",".join(flags) or None, "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=cfg.offer_expiry_hours)).isoformat(),
            "updated_at": now.isoformat(),
        }
        try:
            self.market.create_offer(row)
        except Conflict:
            raise ApiError(409, "You already sent an offer on this job. Update that one instead.") from None
        self.send_json(201, {"ok": True, "offer": self._offer_view(row, False)})

    def _close_other_offers(self, job_id, keep, now):
        for other in self.market.offers_for_job(job_id):
            if other["id"] != keep and other["status"] in offers.OPEN_STATES:
                self.market.update_offer(other["id"], {"status": offers.EXPIRED, "updated_at": now.isoformat()})

    def v1_offer_action(self, offer_id, action):
        user, cfg, now = self.current_user(), self.mconf, _now()
        p = self.read_json() if action == "counter" else {}
        with locks.BOOKING_LOCK if action != "accept" else _null():
            row = self.market.get_offer(offer_id)
            job = self.market.get_job(row["job_id"])
            role = jobs.CUSTOMER if job["customer_id"] == user["id"] else (
                jobs.CLEANER if row["cleaner_id"] == user["id"] else None)
            if role is None:
                raise NotFound("offer")
            if row["status"] in offers.OPEN_STATES and _expired(row, now):
                self.market.update_offer(offer_id, {"status": offers.EXPIRED, "updated_at": now.isoformat()})
                raise ApiError(409, "This offer has expired.")
            if action == "accept":
                return self._accept(offer_id, user, role, now)
            offer = _offer_from_row(row)
            if action == "counter":
                new = offers.counter(offer, role, p.get("priceCents"), cfg)
            elif action == "decline":
                new = offers.decline(offer, role)
            else:
                if role != jobs.CLEANER:
                    raise ApiError(403, "Only the cleaner can withdraw an offer.")
                new = offers.withdraw(offer, user["id"])
            self.market.update_offer(offer_id, {
                "price_cents": new.price_cents, "status": new.status, "counter_rounds": new.counter_rounds,
                "awaiting": new.awaiting, "updated_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=cfg.offer_expiry_hours)).isoformat(),
            })
            self.send_json(200, {"ok": True, "offer": self._offer_view(self.market.get_offer(offer_id), False)})

    def _accept(self, offer_id, user, role, now):
        market = self.market

        def save(booked, accepted):
            market.update_offer(accepted.id, {"status": accepted.status, "updated_at": now.isoformat()})
            market.update_job(booked["id"], {"status": booked["status"], "booked_offer_id": accepted.id,
                                             "price_cents": accepted.price_cents,
                                             "status_updated_at": now.isoformat()})
            self._close_other_offers(booked["id"], keep=accepted.id, now=now)
            bookings.create_booking(market, booked, accepted, self.mconf, now)

        booked, accepted = locks.accept_offer(
            market.get_job, lambda oid: _offer_from_row(market.get_offer(oid)), save,
            offer_id, user["id"], role)
        self.send_json(200, {"ok": True, "job": self._job_view(booked, owner=role == jobs.CUSTOMER),
                             "priceCents": accepted.price_cents})

    # -- admin -----------------------------------------------------------------

    def v1_admin_set_cleaner(self):
        if not self.require_admin_session():
            return
        p = self.read_json()
        user = self.market.find_user_by_email(clean_email(p.get("email")))
        if not user or user["status"] != "active":
            raise NotFound("user")
        if p.get("active") is True and vetting_required():
            record = self.market.get_vetting(user["id"])
            if not record or record["status"] != "approved":
                raise ApiError(409, "Approve this cleaner through vetting first.")
        roles = accounts.roles_of(user)
        roles = roles | {"cleaner"} if p.get("active") is True else roles - {"cleaner"}
        self.market.update_user(user["id"], {"roles": ",".join(sorted(roles))})
        self.send_json(200, {"ok": True, "roles": sorted(roles)})


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
