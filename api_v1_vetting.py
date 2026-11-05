"""Cleaner vetting endpoints. Mixin for AdenCleanHandler.

Identity: Stripe Identity (hosted). Background: Checkr (hosted invitation, staging unless
CHECKR_LIVE_OK=1). Pre-adverse and final adverse notices are sent from Checkr's dashboard;
this API records each step with timestamps and refuses steps out of order.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from marketplace import accounts, vetting
from marketplace.checkr_gateway import CheckrError, CheckrGateway, verify_signature
from marketplace.stripe_gateway import StripeError
from store import NotFound
from validation import ApiError, clean_text

UID = r"(?P<user_id>[0-9a-f]{32})"
VETTING_ROUTES = [
    ("POST", r"/api/v1/cleaner/apply", "v1_cleaner_apply"),
    ("GET", r"/api/v1/cleaner/status", "v1_cleaner_status"),
    ("GET", r"/api/v1/cleaner/disclosure", "v1_cleaner_disclosure"),
    ("POST", r"/api/v1/cleaner/authorize", "v1_cleaner_authorize"),
    ("POST", r"/api/v1/cleaner/identity", "v1_cleaner_identity"),
    ("POST", r"/api/v1/cleaner/background", "v1_cleaner_background"),
    ("POST", r"/api/v1/cleaner/dispute", "v1_cleaner_dispute"),
    ("POST", r"/api/v1/webhooks/checkr", "v1_checkr_webhook"),
    ("GET", r"/api/v1/admin/vetting", "v1_admin_vetting_queue"),
    ("POST", rf"/api/v1/admin/vetting/{UID}", "v1_admin_vetting_decide"),
]

# DRAFT for counsel. The FCRA requires a disclosure "in a document that consists solely of
# the disclosure"; this endpoint serves it on its own screen, separate from the terms.
DISCLOSURE = (
    "Background check disclosure\n\n"
    "AdenClean will obtain a consumer report about you from Checkr, Inc., a consumer reporting agency, "
    "to decide whether you can offer cleaning services through AdenClean. The report may include your "
    "criminal history, sex-offender registry records and identity information. You can ask Checkr for "
    "a copy of your report and dispute anything in it that is wrong.\n\n"
    "If AdenClean may decide not to activate you because of the report, you will first receive a copy of "
    "the report and a summary of your rights, and time to respond.\n\n"
    "DRAFT: to be reviewed by AdenClean's attorney before use."
)

# Tests replace these with fakes.
CHECKR_FACTORY = None


def vetting_required():
    return os.environ.get("VETTING_REQUIRED", "1") != "0"


def _now():
    return datetime.now(timezone.utc)


class VettingRoutes:
    def checkr(self):
        try:
            if CHECKR_FACTORY:
                return CHECKR_FACTORY()
            return CheckrGateway(os.environ.get("CHECKR_API_KEY", ""), os.environ.get("CHECKR_PACKAGE", ""))
        except CheckrError as error:
            raise ApiError(503, str(error)) from error

    def _my_vetting(self, user):
        record = self.market.get_vetting(user["id"])
        if not record:
            raise ApiError(404, "Apply to clean with AdenClean first.")
        return record

    @staticmethod
    def _vetting_view(record):
        keys = ("status", "identity_status", "background_status", "consent_at", "dispute_deadline", "dispute_open")
        return {k: record[k] for k in keys}

    def _vet(self, fn, *args):
        try:
            return fn(*args)
        except vetting.VettingError as error:
            raise ApiError(409, str(error)) from error
        except (StripeError, CheckrError) as error:
            raise ApiError(502, str(error)) from error

    # -- cleaner side ------------------------------------------------------------

    def v1_cleaner_apply(self):
        user = self.current_user()
        if self.read_json().get("over18") is not True:
            raise ApiError(400, "Cleaners must be 18 or older.")
        if self.market.get_vetting(user["id"]):
            raise ApiError(409, "You already applied.")
        record = vetting.new_record(user["id"], _now())
        self.market.save_vetting(record, created=True)
        self.send_json(201, {"ok": True, "vetting": self._vetting_view(record)})

    def v1_cleaner_status(self):
        self.send_json(200, {"ok": True, "vetting": self._vetting_view(self._my_vetting(self.current_user()))})

    def v1_cleaner_disclosure(self):
        self.current_user()
        self.send_json(200, {"ok": True, "version": vetting.DISCLOSURE_VERSION, "text": DISCLOSURE})

    def v1_cleaner_authorize(self):
        user, now = self.current_user(), _now()
        record = self._my_vetting(user)
        p = self.read_json()
        signed = self._vet(vetting.record_consent, record, clean_text(p.get("fullName"), "Full legal name", 120),
                           p.get("authorize"), now)
        self.market.save_vetting(signed)
        self.market.add_consent({"id": uuid.uuid4().hex, "user_id": user["id"], "kind": "background_check",
                                 "version": vetting.DISCLOSURE_VERSION, "ip": self.client_address[0],
                                 "created_at": now.isoformat()})
        self.send_json(200, {"ok": True, "vetting": self._vetting_view(signed)})

    def v1_cleaner_identity(self):
        user = self.current_user()
        record = self._my_vetting(user)
        if record["identity_status"] == "verified":
            raise ApiError(409, "Your identity is already verified.")
        base = os.environ.get("PUBLIC_BASE_URL", "https://adenclean.onrender.com").rstrip("/")
        session = self._vet(self.gateway().create_identity_session, user["id"], f"{base}/?identity=done",
                            f"identity:{user['id']}:{record['identity_status']}")
        self.market.save_vetting(dict(record, identity_status="pending", identity_ref=session["id"],
                                      updated_at=_now().isoformat()))
        self.send_json(200, {"ok": True, "url": session["url"]})

    def v1_cleaner_background(self):
        user = self.current_user()
        record = self._my_vetting(user)
        self._vet(vetting.can_order_background, record)
        gw = self.checkr()
        candidate = self._vet(gw.create_candidate, user["email"], user["id"])
        invitation = self._vet(gw.create_invitation, candidate["id"])
        self.market.save_vetting(dict(record, background_status="invited", candidate_ref=candidate["id"],
                                      updated_at=_now().isoformat()))
        self.send_json(200, {"ok": True, "url": invitation["invitation_url"]})

    def v1_cleaner_dispute(self):
        user = self.current_user()
        record = self._vet(vetting.open_dispute, self._my_vetting(user), _now())
        self.market.save_vetting(record)
        self.send_json(200, {"ok": True, "vetting": self._vetting_view(record)})

    # -- vendor callbacks --------------------------------------------------------------

    def handle_identity_event(self, event):
        obj = event["data"]["object"]
        record = self.market.get_vetting((obj.get("metadata") or {}).get("user_id", ""))
        if not record:
            return "ignored"
        if event["type"] == "identity.verification_session.verified":
            self.market.save_vetting(vetting.apply_identity_result(record, True, _now()))
        elif event["type"] == "identity.verification_session.requires_input":
            self.market.save_vetting(vetting.apply_identity_result(record, False, _now()))
        return "processed"

    def v1_checkr_webhook(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 65_536:
            raise ApiError(400, "Bad webhook body.")
        self._body_read_for = self.headers
        payload = self.rfile.read(length)
        key = os.environ.get("CHECKR_WEBHOOK_KEY") or os.environ.get("CHECKR_API_KEY", "")
        if not verify_signature(payload, self.headers.get("X-Checkr-Signature"), key):
            raise ApiError(400, "Signature does not match.")
        event = json.loads(payload)
        if self.market.has_webhook_event(f"checkr:{event['id']}"):
            return self.send_json(200, {"ok": True, "result": "duplicate"})
        obj = event["data"]["object"]
        if event["type"] == "report.completed":
            record = self.market.vetting_by_candidate(obj.get("candidate_id", ""))
            if record and record["background_status"] in ("invited", "pending"):
                result = "suspended" if obj.get("status") == "suspended" else obj.get("result")
                self.market.save_vetting(self._vet(vetting.apply_background_result, record, result, obj["id"], _now()))
        self.market.record_webhook_event(f"checkr:{event['id']}", event["type"], _now().isoformat())
        self.send_json(200, {"ok": True, "result": "processed"})

    # -- admin review -------------------------------------------------------------------

    def v1_admin_vetting_queue(self):
        if not self.require_admin_session():
            return
        rows = self.market.vetting_queue("in_review") + self.market.vetting_queue("pre_adverse")
        out = []
        for r in rows:
            try:
                name = self.market.get_user(r["id"])["display_name"]
            except NotFound:
                name = "Unknown"
            out.append(dict(self._vetting_view(r), user_id=r["id"], name=name, report_ref=r["report_ref"]))
        self.send_json(200, {"ok": True, "queue": out, "reasons": vetting.REASONS})

    def v1_admin_vetting_decide(self, user_id):
        if not self.require_admin_session():
            return
        p, now, admin = self.read_json(), _now(), self.admin["email"]
        record = self.market.get_vetting(user_id)
        if not record:
            raise ApiError(404, "No application for that person.")
        action, note = p.get("action"), p.get("note") or ""
        if action in ("pre_adverse", "final_adverse") and p.get("noticeSentViaCheckr") is not True:
            raise ApiError(400, "Send the notice from the Checkr dashboard first, then confirm it here.")
        steps = {
            "approve": lambda: vetting.approve(record, admin, note, now),
            "pre_adverse": lambda: vetting.pre_adverse(record, admin, p.get("reason"), note, now),
            "final_adverse": lambda: vetting.final_adverse(record, admin, now),
            "resolve_dispute": lambda: vetting.resolve_dispute(record, admin, now),
            "decline_identity": lambda: vetting.decline_identity(record, admin, note, now),
        }
        if action not in steps:
            raise ApiError(400, "Choose a valid action.")
        updated = self._vet(steps[action])
        self.market.save_vetting(updated)
        if updated["status"] == "approved":
            user = self.market.get_user(user_id)
            self.market.update_user(user_id, {"roles": ",".join(sorted(accounts.roles_of(user) | {"cleaner"}))})
        self.send_json(200, {"ok": True, "vetting": self._vetting_view(updated)})
