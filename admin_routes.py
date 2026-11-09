"""Admin endpoints: sign-in sessions and record review."""

import hashlib
import hmac
import os
import re
import time
import uuid
from datetime import datetime, timezone
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlsplit

import auth
from store import Conflict, NotFound
from validation import RECORD_STATUSES, RECORD_TYPES, STATUS_TRANSITIONS, ApiError, clean_text

ADMIN_SESSION_COOKIE = "adenclean_admin_session"
ADMIN_SESSION_SECONDS = 8 * 60 * 60
ADMIN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class AdminRoutes:
    """Mixin for AdenCleanHandler; reads storage through self.store."""

    # -- admin authentication --------------------------------------------------

    def admin_setup_message(self):
        if not os.environ.get("SESSION_SECRET"):
            return "SESSION_SECRET is not available to the app. Add it to the app's secrets and restart."
        if not self.store.has_admins():
            return "No admin accounts exist yet. Create the first one with: python create_admin.py you@example.com"
        return ""

    def admin_secret_is_configured(self):
        return bool(os.environ.get("SESSION_SECRET"))

    @staticmethod
    def sign_session(payload):
        return hmac.new(
            os.environ["SESSION_SECRET"].encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def make_admin_session(self, admin_id):
        expires_at = int(time.time()) + ADMIN_SESSION_SECONDS
        session_payload = f"{expires_at}.{admin_id}.{uuid.uuid4().hex}"
        return f"{session_payload}.{self.sign_session(session_payload)}"

    def current_admin(self):
        """Return the signed-in admin's record, or None."""
        if not self.admin_secret_is_configured():
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            session = cookie.get(ADMIN_SESSION_COOKIE)
        except CookieError:
            return None
        if session is None:
            return None

        parts = session.value.split(".")
        if len(parts) != 4 or not parts[0].isdigit():
            return None
        expires_at, admin_id, nonce, supplied_signature = parts
        if int(expires_at) < int(time.time()):
            return None
        if not ADMIN_ID_PATTERN.fullmatch(admin_id) or len(nonce) != 32:
            return None
        expected_signature = self.sign_session(f"{expires_at}.{admin_id}.{nonce}")
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None

        admin = self.store.get_admin(admin_id)
        if admin is None or admin.get("active") != 1 or admin.get("role") != "admin":
            return None
        return admin

    def require_admin_session(self):
        if not self.admin_secret_is_configured():
            self.send_json(503, {"ok": False, "error": self.admin_setup_message()})
            return False
        self.admin = self.current_admin()
        if self.admin is None:
            self.send_json(401, {"ok": False, "error": "Sign in to continue."})
            return False
        return True

    def create_admin_session(self):
        if not self.admin_secret_is_configured():
            self.send_json(503, {"ok": False, "error": self.admin_setup_message()})
            return

        payload = self.read_json()
        email = payload.get("email")
        password = payload.get("password")
        if (
            not isinstance(email, str)
            or not isinstance(password, str)
            or len(email) > 254
            or len(password) > auth.PASSWORD_MAX_LENGTH
        ):
            raise ApiError(400, "Enter your email and password.")

        admin = self.store.get_admin_by_email(email.strip().lower())
        if (
            admin is not None
            and admin.get("active") == 1
            and admin.get("role") == "admin"
            and auth.verify_password(password, admin["password_hash"])
        ):
            cookie = (
                f"{ADMIN_SESSION_COOKIE}={self.make_admin_session(admin['id'])}; "
                f"Max-Age={ADMIN_SESSION_SECONDS}; Path=/api/admin; "
                "HttpOnly; Secure; SameSite=Strict"
            )
            self.send_json(
                200,
                {"ok": True, "authenticated": True},
                headers={"Set-Cookie": cookie},
            )
            return

        if admin is None:
            auth.burn_time(password)  # same cost whether or not the email exists
        self.send_json(401, {"ok": False, "error": "The email or password is incorrect."})

    def clear_admin_session(self):
        cookie = (
            f"{ADMIN_SESSION_COOKIE}=; Max-Age=0; Path=/api/admin; "
            "HttpOnly; Secure; SameSite=Strict"
        )
        self.send_json(200, {"ok": True}, headers={"Set-Cookie": cookie})

    # -- admin records -----------------------------------------------------------

    def list_admin_records(self):
        parameters = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        record_type = parameters.get("type", ["requests"])[0]
        status_filter = parameters.get("status", ["all"])[0]
        if record_type not in RECORD_TYPES:
            self.send_json(400, {"ok": False, "error": "Choose a valid record type."})
            return
        if status_filter != "all" and status_filter not in RECORD_STATUSES[record_type]:
            self.send_json(400, {"ok": False, "error": "Choose a valid status filter."})
            return

        records, counts, histories = self.store.list_records(
            record_type, status_filter, sorted(RECORD_STATUSES[record_type])
        )
        for record in records:
            record["history"] = [
                {
                    "oldStatus": entry["old_status"],
                    "newStatus": entry["new_status"],
                    "note": entry["note"],
                    "actor": entry["actor"],
                    "createdAt": entry["created_at"],
                }
                for entry in histories.get(record["id"], [])
            ]
        self.send_json(
            200,
            {
                "ok": True,
                "type": record_type,
                "status": status_filter,
                "counts": counts,
                "records": records,
            },
        )

    def update_admin_assignment(self):
        """Set or clear who is handling a customer request. The status is left alone."""
        payload = self.read_json()
        record_id = clean_text(payload.get("id"), "Record reference", 32).upper()
        assigned_to = clean_text(payload.get("assignedTo", ""), "Assigned to", 100, required=False)
        try:
            current_status = self.store.get_status("requests", record_id)
        except NotFound as error:
            raise ApiError(404, "That record could not be found.") from error
        changed_at = datetime.now(timezone.utc).isoformat()
        try:
            self.store.set_assignment(
                record_id,
                assigned_to,
                {
                    "record_type": "requests",
                    "record_id": record_id,
                    "old_status": current_status,
                    "new_status": current_status,
                    "note": f"Assigned to {assigned_to}" if assigned_to else "Assignment cleared",
                    "actor": self.admin["email"],
                    "created_at": changed_at,
                },
            )
        except NotFound as error:
            raise ApiError(404, "That record could not be found.") from error
        self.send_json(200, {"ok": True, "reference": record_id, "assignedTo": assigned_to,
                             "message": "Assignment saved."})

    def update_admin_record(self):
        payload = self.read_json()
        record_type = clean_text(payload.get("type"), "Record type", 20)
        if record_type not in RECORD_TYPES:
            raise ApiError(400, "Choose a valid record type.")

        record_id = clean_text(payload.get("id"), "Record reference", 32).upper()
        new_status = clean_text(payload.get("status"), "Status", 20).lower()
        if new_status not in RECORD_STATUSES[record_type]:
            raise ApiError(400, "Choose a valid status.")
        expected_status = clean_text(payload.get("expectedStatus"), "Current status", 20).lower()
        if expected_status not in RECORD_STATUSES[record_type]:
            raise ApiError(400, "The current status is invalid.")
        note = clean_text(
            payload.get("note", ""),
            "Status note",
            240,
            required=False,
            allow_newlines=True,
        )
        changed_at = datetime.now(timezone.utc).isoformat()

        try:
            current_status = self.store.get_status(record_type, record_id)
        except NotFound as error:
            raise ApiError(404, "That record could not be found.") from error
        if current_status != expected_status:
            raise ApiError(409, "This record changed. Refresh the list and try again.")
        if new_status == current_status:
            raise ApiError(400, "Choose a different status.")
        if new_status not in STATUS_TRANSITIONS[record_type][current_status]:
            raise ApiError(400, "That status change is not allowed.")

        try:
            self.store.set_status(
                record_type,
                record_id,
                current_status,
                new_status,
                changed_at,
                {
                    "record_type": record_type,
                    "record_id": record_id,
                    "old_status": current_status,
                    "new_status": new_status,
                    "note": note,
                    "actor": self.admin["email"],
                    "created_at": changed_at,
                },
            )
        except NotFound as error:
            raise ApiError(404, "That record could not be found.") from error
        except Conflict as error:
            raise ApiError(409, "This record changed. Refresh the list and try again.") from error

        self.send_json(
            200,
            {
                "ok": True,
                "reference": record_id,
                "status": new_status,
                "message": "Status updated.",
            },
        )

