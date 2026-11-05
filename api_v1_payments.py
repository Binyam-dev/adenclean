"""Marketplace payment endpoints (Stripe test mode). Mixin for AdenCleanHandler.

Payments are active only when PAYMENTS_ENABLED=1 and STRIPE_SECRET_KEY is a test key
(live keys also need STRIPE_LIVE_OK=1). The webhook verifies Stripe's signature before
reading anything.
"""

import os
from datetime import datetime, timezone

from marketplace import bookings, jobs, money
from marketplace.stripe_gateway import StripeError, StripeGateway, verify_webhook
from store import NotFound
from validation import ApiError

JOB = r"(?P<job_id>[0-9a-f]{32})"
PAYMENT_ROUTES = [
    ("POST", r"/api/v1/payouts/onboard", "v1_payouts_onboard"),
    ("POST", r"/api/v1/payouts/refresh", "v1_payouts_refresh"),
    ("GET", rf"/api/v1/jobs/{JOB}/booking", "v1_booking"),
    ("POST", rf"/api/v1/jobs/{JOB}/pay", "v1_pay"),
    ("POST", rf"/api/v1/jobs/{JOB}/check-in", "v1_check_in"),
    ("POST", rf"/api/v1/jobs/{JOB}/check-out", "v1_check_out"),
    ("POST", rf"/api/v1/jobs/{JOB}/confirm", "v1_confirm"),
    ("POST", rf"/api/v1/jobs/{JOB}/cancel-booking", "v1_cancel_booking"),
    ("POST", rf"/api/v1/jobs/{JOB}/tip", "v1_tip"),
    ("POST", r"/api/v1/webhooks/stripe", "v1_stripe_webhook"),
    ("POST", r"/api/v1/admin/release-due", "v1_admin_release_due"),
]

# Tests swap this for a fake. Production builds a real (test-mode) gateway from the env.
GATEWAY_FACTORY = None


def payments_enabled():
    return os.environ.get("PAYMENTS_ENABLED") == "1"


def _now():
    return datetime.now(timezone.utc)


class PaymentRoutes:
    def gateway(self):
        if not payments_enabled():
            raise ApiError(503, "Payments are not turned on yet.")
        try:
            return GATEWAY_FACTORY() if GATEWAY_FACTORY else StripeGateway(os.environ.get("STRIPE_SECRET_KEY", ""))
        except StripeError as error:
            raise ApiError(503, str(error)) from error

    def _booking_for(self, job_id, user):
        booking = bookings.get_booking(self.market, job_id)
        if user["id"] == booking["customer_id"]:
            return booking, jobs.CUSTOMER
        if user["id"] == booking["cleaner_id"]:
            return booking, jobs.CLEANER
        raise NotFound("booking")

    def _booking_view(self, booking, role):
        split = money.split_payment(booking["price_cents"], bookings._rate(booking), booking["tip_cents"])
        view = {k: booking[k] for k in ("job_id", "price_cents", "tip_cents", "payment_status", "payout_status",
                                        "starts_on", "checked_in_at", "checked_out_at", "confirmed_at", "cancelled_by")}
        if role == jobs.CLEANER:
            view.update(fee_cents=split["platform_fee_cents"], payout_cents=split["cleaner_payout_cents"])
        else:
            view.update(total_cents=split["customer_pays_cents"])
        return view

    def _call_stripe(self, fn, *args):
        try:
            return fn(*args)
        except StripeError as error:
            raise ApiError(502, f"Payment provider: {error}") from error
        except bookings.BookingError as error:
            raise ApiError(409, str(error)) from error

    # -- cleaner payouts ---------------------------------------------------------

    def v1_payouts_onboard(self):
        user = self.current_user()
        self._require_cleaner(user)
        gw, now = self.gateway(), _now()
        account = self.market.payout_account(user["id"])
        if not account:
            created = self._call_stripe(gw.create_account, user["email"], f"acct:{user['id']}")
            account = {"user_id": user["id"], "stripe_account_id": created["id"],
                       "payouts_enabled": 1 if created.get("payouts_enabled") else 0, "updated_at": now.isoformat()}
            self.market.save_payout_account(dict(account, id=user["id"]))
        base = os.environ.get("PUBLIC_BASE_URL", "https://adenclean.onrender.com").rstrip("/")
        link = self._call_stripe(gw.account_link, account["stripe_account_id"],
                                 f"{base}/?payouts=retry", f"{base}/?payouts=done")
        self.send_json(200, {"ok": True, "url": link["url"]})

    def v1_payouts_refresh(self):
        user = self.current_user()
        account = self.market.payout_account(user["id"])
        if not account:
            raise ApiError(404, "Set up payouts first.")
        remote = self._call_stripe(self.gateway().retrieve_account, account["stripe_account_id"])
        enabled = 1 if remote.get("payouts_enabled") else 0
        self.market.save_payout_account({"user_id": user["id"], "stripe_account_id": account["stripe_account_id"],
                                         "payouts_enabled": enabled, "updated_at": _now().isoformat()})
        self.send_json(200, {"ok": True, "payoutsEnabled": bool(enabled)})

    def require_payouts_ready(self, user):
        """Cleaners must finish payout setup before quoting, so a booked job can always be paid out."""
        if not payments_enabled():
            return
        account = self.market.payout_account(user["id"])
        if not account or not account["payouts_enabled"]:
            raise ApiError(403, "Finish setting up payouts before you send offers.")

    # -- booking lifecycle -------------------------------------------------------

    def v1_booking(self, job_id):
        user = self.current_user()
        booking, role = self._booking_for(job_id, user)
        self.send_json(200, {"ok": True, "booking": self._booking_view(booking, role)})

    def v1_pay(self, job_id):
        user = self.current_user()
        booking, role = self._booking_for(job_id, user)
        if role != jobs.CUSTOMER:
            raise ApiError(403, "Only the customer pays for a booking.")
        secret = self._call_stripe(bookings.start_payment, self.market, self.gateway(), booking, _now())
        self.send_json(200, {"ok": True, "clientSecret": secret,
                             "publishableKey": os.environ.get("STRIPE_PUBLISHABLE_KEY", "")})

    def v1_check_in(self, job_id):
        user = self.current_user()
        booking, _ = self._booking_for(job_id, user)
        self._call_stripe(bookings.check_in, self.market, booking, user["id"], _now())
        self.send_json(200, {"ok": True})

    def v1_check_out(self, job_id):
        user = self.current_user()
        booking, _ = self._booking_for(job_id, user)
        self._call_stripe(bookings.check_out, self.market, booking, user["id"], _now())
        self.send_json(200, {"ok": True})

    def v1_confirm(self, job_id):
        user = self.current_user()
        booking, role = self._booking_for(job_id, user)
        if role != jobs.CUSTOMER:
            raise ApiError(403, "Only the customer confirms the cleaning is done.")
        self._call_stripe(bookings.release, self.market, self.gateway(), booking, jobs.CUSTOMER, self.mconf, _now())
        self.send_json(200, {"ok": True})

    def v1_cancel_booking(self, job_id):
        user = self.current_user()
        booking, role = self._booking_for(job_id, user)
        has_body = int(self.headers.get("Content-Length") or 0) > 0
        waived = role == jobs.CLEANER and has_body and self.read_json().get("waiveFee") is True
        gw = self.gateway() if booking["payment_status"] == "paid" else None
        result = self._call_stripe(bookings.cancel, self.market, gw, booking,
                                   "customer" if role == jobs.CUSTOMER else "cleaner", self.mconf, _now(), waived)
        self.send_json(200, {"ok": True, "refundCents": result["refund_cents"], "cleanerFeeCents": result["cleaner_fee_cents"]})

    def v1_tip(self, job_id):
        user = self.current_user()
        booking, role = self._booking_for(job_id, user)
        if role != jobs.CUSTOMER:
            raise ApiError(403, "Only the customer can tip.")
        secret = self._call_stripe(bookings.start_tip, self.market, self.gateway(), booking,
                                   self.read_json().get("tipCents"), self.mconf, _now())
        self.send_json(200, {"ok": True, "clientSecret": secret})

    # -- Stripe webhook and admin sweep -----------------------------------------------

    def v1_stripe_webhook(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 65_536:
            raise ApiError(400, "Bad webhook body.")
        self._body_read_for = self.headers
        payload = self.rfile.read(length)
        try:
            event = verify_webhook(payload, self.headers.get("Stripe-Signature"), os.environ.get("STRIPE_WEBHOOK_SECRET", ""))
        except StripeError as error:
            raise ApiError(400, str(error)) from error
        result = self._call_stripe(bookings.handle_event, self.market, self.gateway(), event, _now())
        self.send_json(200, {"ok": True, "result": result})

    def v1_admin_release_due(self):
        if not self.require_admin_session():
            return
        gw, now, released = self.gateway(), _now(), 0
        for booking in self.market.bookings_awaiting_release():
            try:
                bookings.release(self.market, gw, booking, jobs.SYSTEM, self.mconf, now)
                released += 1
            except (bookings.BookingError, jobs.TransitionError):
                continue  # not due yet, or disputed
        self.send_json(200, {"ok": True, "released": released})
