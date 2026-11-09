"""Report and block endpoints, and the admin moderation queue. Mixin for AdenCleanHandler.

Reports and blocks name a job or an offer, never a user id (the API exposes no user ids).
The admin endpoints are reached at /api/admin/moderation (main.py maps that to the /api/v1
path below), because the admin session cookie is only sent under /api/admin.
All moderation writes run under BOOKING_LOCK so they cannot race with accepting an offer.
"""

import uuid
from datetime import datetime, timezone

from marketplace import accounts, bookings, jobs, locks, mailer, moderation, offers
from marketplace.stripe_gateway import StripeError
from store import Conflict, NotFound
from validation import ApiError, clean_text

ID = r"[0-9a-f]{32}"
MODERATION_ROUTES = [
    ("POST", r"/api/v1/reports", "v1_create_report"),
    ("POST", rf"/api/v1/jobs/(?P<target_id>{ID})/block", "v1_block_via_job"),
    ("POST", rf"/api/v1/offers/(?P<target_id>{ID})/block", "v1_block_via_offer"),
    ("GET", r"/api/v1/blocks", "v1_list_blocks"),
    ("POST", rf"/api/v1/blocks/(?P<block_id>{ID})/remove", "v1_remove_block"),
    ("GET", r"/api/v1/admin/moderation", "v1_admin_moderation_queue"),
    ("POST", rf"/api/v1/admin/moderation/(?P<report_id>{ID})", "v1_admin_moderation_act"),
]
ADMIN_ACTIONS = ("dismiss", "remove_content", "suspend_user", "unsuspend_user", "cancel_booking_refund")


def _now():
    return datetime.now(timezone.utc)


class ModerationRoutes:
    # -- who and what a person may report or block ---------------------------------------

    def _job_and_offer(self, kind, target_id):
        """The job and (for an offer) the offer, or NotFound."""
        if kind == "job":
            return self.market.get_job(target_id), None
        offer = self.market.get_offer(target_id)
        return self.market.get_job(offer["job_id"]), offer

    def _can_report(self, user, job, offer):
        """You may report what you can see: a job you posted or can bid on, or an offer on your
        job or by you. Blocked and closed items stay reportable."""
        uid = user["id"]
        if offer is not None:
            return uid in (job["customer_id"], offer["cleaner_id"])
        if job["customer_id"] == uid:
            return True
        if "cleaner" not in accounts.roles_of(user):
            return False
        return job["status"] == "open" or any(o["cleaner_id"] == uid for o in self.market.offers_for_job(job["id"]))

    def _author_of(self, job, offer):
        return offer["cleaner_id"] if offer is not None else job["customer_id"]

    # -- reporting -----------------------------------------------------------------------

    def v1_create_report(self):
        user, now = self.current_user(), _now()
        p = self.read_json()
        kind = p.get("targetKind")
        if kind not in moderation.REPORT_TARGETS:
            raise ApiError(400, "Choose what you are reporting.")
        target_id = clean_text(p.get("targetId"), "Target", 40)
        try:
            reason = moderation.clean_reason(p.get("reason"))
        except moderation.ModerationError as error:
            raise ApiError(400, str(error)) from error
        detail = clean_text(p.get("detail") or "", "Detail", 500, required=False, allow_newlines=True) or None
        with locks.BOOKING_LOCK:
            try:
                job, offer = self._job_and_offer(kind, target_id)
            except NotFound:
                raise NotFound("target") from None
            if not self._can_report(user, job, offer):
                raise NotFound("target")  # same answer as a missing target
            author = self._author_of(job, offer)
            if author == user["id"]:
                raise ApiError(400, "You cannot report your own content.")
            for existing in self.market.reports_by_reporter(user["id"]):
                if existing["status"] == "open" and existing["target_kind"] == kind and existing["target_id"] == target_id:
                    return self.send_json(200, {"ok": True, "merged": True, "reportId": existing["id"]})
            if moderation.reports_left(self.market, user["id"], now) <= 0:
                raise ApiError(429, "You have sent a lot of reports. Please wait an hour.")
            try:
                author_name = self.market.get_user(author)["display_name"]
            except NotFound:
                author_name = "Unknown"
            text = (offer["message"] if offer is not None else job["notes"]) or None
            report = {
                "id": uuid.uuid4().hex, "reporter_id": user["id"], "target_kind": kind, "target_id": target_id,
                "target_user_id": author, "reason": reason, "detail": detail, "snapshot_text": text,
                "snapshot_name": author_name, "snapshot_status": (offer or job)["status"],
                "status": "open", "action": None, "created_at": now.isoformat(),
                "resolved_at": None, "resolved_by": None,
            }
            self.market.create_report(report)
        # The email never names the reporter or the reported person.
        mailer.send_alert("AdenClean: new report to review",
                          f"A {kind} was reported ({moderation.REASONS[reason]}). "
                          "Open the admin page and check the Reports tab. Reports are answered within 24 hours.")
        self.send_json(201, {"ok": True, "merged": False, "reportId": report["id"]})

    # -- blocking ------------------------------------------------------------------------

    def _block(self, kind, target_id):
        user, now = self.current_user(), _now()
        self.enforce_rate_limit(bucket="v1-block:" + user["id"], limit=30,
                                message="Too many block requests. Please wait.")
        with locks.BOOKING_LOCK:
            job, offer = self._job_and_offer(kind, target_id)
            uid = user["id"]
            if offer is not None:
                if uid == job["customer_id"]:
                    other = offer["cleaner_id"]
                elif uid == offer["cleaner_id"]:
                    other = job["customer_id"]
                else:
                    raise NotFound("offer")
            else:
                if job["customer_id"] == uid:
                    raise ApiError(400, "You cannot block yourself.")
                if not self._can_report(user, job, None):
                    raise NotFound("job")
                other = job["customer_id"]
            if other == uid:
                raise ApiError(400, "You cannot block yourself.")
            # Write the block first, then sweep: a missed sweep cannot leak, because every
            # read checks the block row.
            existing = self.market.get_block(uid, other)
            if existing is None:
                block_id = uuid.uuid4().hex
                try:
                    self.market.create_block({"id": block_id, "blocker_id": uid, "blocked_id": other,
                                              "active": 1, "created_at": now.isoformat()})
                except Conflict:
                    existing = self.market.get_block(uid, other)
                    block_id = existing["id"]
            else:
                block_id = existing["id"]
                if not existing["active"]:
                    self.market.update_block(block_id, {"active": 1})
            self._sweep_pair(uid, other, now)
        self.send_json(200, {"ok": True, "blockId": block_id})

    def _sweep_pair(self, a, b, now):
        """Withdraw open offers between a blocked pair, in both directions (idempotent).
        Offers on a job that already has a booking between them are left alone."""
        for customer, cleaner in ((a, b), (b, a)):
            for job in self.market.jobs_for_customer(customer):
                if job["status"] != "open":
                    continue
                for offer in self.market.offers_for_job(job["id"]):
                    if offer["cleaner_id"] == cleaner and offer["status"] in offers.OPEN_STATES:
                        self.market.update_offer(offer["id"], {"status": offers.WITHDRAWN, "updated_at": now.isoformat()})

    def v1_block_via_job(self, target_id):
        self._block("job", target_id)

    def v1_block_via_offer(self, target_id):
        self._block("offer", target_id)

    def v1_list_blocks(self):
        user = self.current_user()
        out = []
        for block in self.market.blocks_by(user["id"]):
            try:
                name = self.market.get_user(block["blocked_id"])["display_name"]
            except NotFound:
                name = "Unknown"
            out.append({"id": block["id"], "name": name, "created_at": block["created_at"]})
        self.send_json(200, {"ok": True, "blocks": out})

    def v1_remove_block(self, block_id):
        user = self.current_user()
        with locks.BOOKING_LOCK:
            block = self.market.get_block_by_id(block_id)
            if block["blocker_id"] != user["id"]:
                raise NotFound("block")
            self.market.update_block(block_id, {"active": 0})  # withdrawn offers are not restored
        self.send_json(200, {"ok": True})

    # -- admin ---------------------------------------------------------------------------

    def v1_admin_moderation_queue(self):
        if not self.require_admin_session():
            return
        queue = []
        for r in self.market.reports_with_status("open"):
            about = [x for x in self.market.reports_about_user(r["target_user_id"]) if x["status"] == "open"]
            queue.append({k: r[k] for k in ("id", "target_kind", "target_id", "reason", "detail", "snapshot_text",
                                            "snapshot_name", "snapshot_status", "created_at")}
                         | {"reason_label": moderation.REASONS.get(r["reason"], r["reason"]),
                            "open_reports_about_author": len(about)})
        self.send_json(200, {"ok": True, "queue": queue, "actions": list(ADMIN_ACTIONS)})

    def v1_admin_moderation_act(self, report_id):
        if not self.require_admin_session():
            return
        p, now, admin = self.read_json(), _now(), self.admin["email"]
        action = p.get("action")
        if action not in ADMIN_ACTIONS:
            raise ApiError(400, "Choose a valid action.")
        warning = None
        with locks.BOOKING_LOCK:
            report = self.market.get_report(report_id)
            if report["status"] != "open":
                raise ApiError(409, "This report was already handled.")
            job, offer = self._job_and_offer(report["target_kind"], report["target_id"])
            author = report["target_user_id"]
            if action == "dismiss":
                pass
            elif action == "remove_content":
                if offer is not None:
                    self.market.update_offer(offer["id"], {"message": None, "updated_at": now.isoformat()})
                else:
                    self.market.update_job(job["id"], {"notes": None, "status_updated_at": now.isoformat()})
            elif action == "suspend_user":
                try:
                    accounts.suspend(self.market, self.market.get_user(author), now)
                except accounts.AuthError as error:
                    raise ApiError(error.status, error.message) from error
                if self._live_booking_for(author):
                    warning = "This person has a live booking. It continues; use cancel and refund if it should stop."
            elif action == "unsuspend_user":
                try:
                    accounts.unsuspend(self.market, self.market.get_user(author))
                except accounts.AuthError as error:
                    raise ApiError(error.status, error.message) from error
            else:  # cancel_booking_refund
                self._admin_cancel_booking(job, now)
            status = "dismissed" if action == "dismiss" else "actioned"
            self.market.update_report(report_id, {"status": status, "action": action,
                                                  "resolved_at": now.isoformat(), "resolved_by": admin})
        self.send_json(200, {"ok": True, "status": status, "warning": warning})

    def _live_booking_for(self, user_id):
        for column in ("customer_id", "cleaner_id"):
            for booking in self.market.t.find("bookings", {column: user_id}):
                if booking.get("cancelled_by"):
                    continue
                if self.market.get_job(booking["job_id"])["status"] in moderation.ACTIVE_BOOKING_JOB_STATUSES:
                    return True
        return False

    def _admin_cancel_booking(self, job, now):
        booking = self.market.booking_for_job(job["id"])
        if not booking or booking.get("cancelled_by"):
            raise ApiError(409, "This job has no live booking to cancel.")
        try:
            gateway = self.gateway() if booking["payment_status"] == "paid" else None
            # A full refund with no late fee, as if the customer cancelled and the cleaner waived it.
            bookings.cancel(self.market, gateway, booking, "customer", self.mconf, now, True)
        except (bookings.BookingError, jobs.TransitionError) as error:
            raise ApiError(409, str(error) or "This job cannot be cancelled in its current state.") from error
        except StripeError as error:
            raise ApiError(502, f"Payment provider: {error}") from error
