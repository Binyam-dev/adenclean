import json
import hmac
import os
import re
import secrets
import threading
import time
import uuid
import hashlib
from datetime import date, datetime, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import auth
import store as storage
from store import Conflict, NotFound, StoreError


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_MAX_REQUESTS = 10
ADMIN_SESSION_COOKIE = "adenclean_admin_session"
ADMIN_SESSION_SECONDS = 8 * 60 * 60
ADMIN_RATE_LIMIT_MAX_REQUESTS = 120
LOGIN_RATE_LIMIT_MAX_REQUESTS = 10
LOOKUP_RATE_LIMIT_MAX_REQUESTS = 90  # read-only status checks from the app
RATE_LIMITS = {}
STORE = None
RATE_LIMIT_LOCK = threading.Lock()
ADMIN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
DEFAULT_PORT = 5000
SERVICE_TYPES = {
    "routine": "Routine home cleaning",
    "deep": "Deep cleaning",
    "move-in/move-out": "Move-in / move-out",
    "move-in-move-out": "Move-in / move-out",
    "move-in-out": "Move-in / move-out",
}
PREFERRED_TIMES = {"morning", "afternoon", "flexible"}
RECORD_TYPES = storage.RECORD_TABLES
RECORD_STATUSES = {
    "requests": {"pending", "approved", "declined", "completed", "cancelled"},
    "availability": {"pending", "approved", "declined"},
    "reviews": {"new", "reviewed"},
    "issues": {"open", "in_review", "resolved"},
}
STATUS_TRANSITIONS = {
    "requests": {
        "pending": {"approved", "declined", "cancelled"},
        "approved": {"pending", "completed", "cancelled"},
        "declined": {"pending"},
        "completed": set(),
        "cancelled": {"pending"},
    },
    "availability": {
        "pending": {"approved", "declined"},
        "approved": set(),
        "declined": {"pending"},
    },
    "reviews": {
        "new": {"reviewed"},
        "reviewed": set(),
    },
    "issues": {
        "open": {"in_review", "resolved"},
        "in_review": {"open", "resolved"},
        "resolved": {"in_review"},
    },
}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def clean_text(value, label, max_length, required=True, allow_newlines=False):
    if not isinstance(value, str):
        raise ApiError(400, f"{label} is required.")

    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if allow_newlines:
        value = re.sub(r"[^\S\n]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
    else:
        value = " ".join(value.split())

    value = value.strip()
    if required and not value:
        raise ApiError(400, f"{label} is required.")
    if len(value) > max_length:
        raise ApiError(400, f"{label} must be {max_length} characters or fewer.")
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise ApiError(400, f"{label} contains unsupported characters.")
    return value


def clean_email(value):
    email = clean_text(value, "Email", 254).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
        raise ApiError(400, "Enter a valid email address.")
    return email


def clean_service_type(value):
    service_type = clean_text(value, "Service type", 40).lower().replace("_", "-")
    if service_type not in SERVICE_TYPES:
        raise ApiError(400, "Choose one of the listed service types.")
    return "move-in/move-out" if service_type.startswith("move-in") else service_type


def clean_date(value, label):
    date_value = clean_text(value, label, 10)
    try:
        parsed_date = date.fromisoformat(date_value)
    except ValueError as error:
        raise ApiError(400, f"Choose a valid {label.lower()}.") from error
    if parsed_date < date.today():
        raise ApiError(400, f"{label} must be today or later.")
    return parsed_date.isoformat()


def clean_time(value, label):
    time_value = clean_text(value, label, 5)
    try:
        parsed_time = datetime.strptime(time_value, "%H:%M")
    except ValueError as error:
        raise ApiError(400, f"Choose a valid {label.lower()}.") from error
    return parsed_time.strftime("%H:%M")


def clean_consent(value):
    if value is not True:
        raise ApiError(400, "Please confirm the submission notice.")
    return 1


def proxy_hops(environ=None):
    """How many reverse proxies sit in front of the app (0 = none, the default)."""
    environ = os.environ if environ is None else environ
    try:
        return max(0, min(int(environ.get("ADENCLEAN_PROXY_HOPS", "0")), 5))
    except ValueError:
        return 0


def client_address(socket_address, forwarded_for, hops):
    """The address to rate-limit.

    With no proxy, that is the socket peer. Behind ``hops`` trusted proxies each one
    appends the address it saw, so the real client is the ``hops``-th entry from the
    right; anything a client put further left in X-Forwarded-For is ignored.
    """
    if hops <= 0 or not forwarded_for:
        return socket_address
    entries = [entry.strip() for entry in forwarded_for.split(",") if entry.strip()]
    if len(entries) < hops:
        return socket_address
    return entries[-hops][:64]


class AdenCleanHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        if proxy_hops():  # served over HTTPS by the proxy
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_json(self, status, payload, headers=None):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "Send the form as JSON.")

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ApiError(400, "The request body is invalid.") from error

        if content_length <= 0:
            raise ApiError(400, "The request body is empty.")
        if content_length > MAX_BODY_BYTES:
            raise ApiError(413, "The submission is too large.")

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(400, "The request body is not valid JSON.") from error

        if not isinstance(payload, dict):
            raise ApiError(400, "The request body must be an object.")
        return payload

    def enforce_rate_limit(self, bucket="public", limit=RATE_LIMIT_MAX_REQUESTS,
                           message="Too many submissions. Please try again later."):
        now = time.monotonic()
        key = (
            bucket,
            client_address(
                self.client_address[0], self.headers.get("X-Forwarded-For", ""), proxy_hops()
            ),
        )
        with RATE_LIMIT_LOCK:
            for stored_key, timestamps in list(RATE_LIMITS.items()):
                recent = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECONDS]
                if recent:
                    RATE_LIMITS[stored_key] = recent
                else:
                    RATE_LIMITS.pop(stored_key, None)
            recent_requests = RATE_LIMITS.get(key, [])
            if len(recent_requests) >= limit:
                raise ApiError(429, message)
            recent_requests.append(now)
            RATE_LIMITS[key] = recent_requests

    def send_storage_error(self, message):
        self.send_json(500, {"ok": False, "error": message})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/admin/session":
            try:
                setup_message = self.admin_setup_message()
                if setup_message:
                    payload = {
                        "ok": True,
                        "configured": False,
                        "authenticated": False,
                        "message": setup_message,
                    }
                else:
                    payload = {
                        "ok": True,
                        "configured": True,
                        "authenticated": self.current_admin() is not None,
                    }
            except StoreError:
                self.send_storage_error("The request could not be completed. Please try again.")
                return
            self.send_json(200, payload)
            return

        if path == "/api/admin/records":
            try:
                if not self.require_admin_session():
                    return
                self.list_admin_records()
            except ApiError as error:
                self.send_json(error.status, {"ok": False, "error": error.message})
            except StoreError:
                self.send_storage_error("The records could not be loaded. Please try again.")
            return

        if path == "/healthz":
            self.send_json(200, {"ok": True})
            return

        if path.startswith("/api/"):
            self.send_json(405, {"ok": False, "error": "This API only accepts submissions."})
            return
        if path == "/admin":
            self.send_response(302)
            self.send_header("Location", "/admin.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/customer-feedback":
            try:
                payload = self.read_json()
                if payload.get("action") == "lookup":
                    # Checking status only reads, and the app checks every saved request.
                    self.enforce_rate_limit(bucket="lookup", limit=LOOKUP_RATE_LIMIT_MAX_REQUESTS)
                else:
                    self.enforce_rate_limit()
                status, result = self.handle_customer_feedback(payload)
                self.send_json(status, result)
            except ApiError as error:
                self.send_json(error.status, {"ok": False, "error": error.message})
            except StoreError:
                self.send_storage_error("The feedback could not be saved. Please try again.")
            return

        if path in {"/api/admin/session", "/api/admin/logout", "/api/admin/records"}:
            try:
                if path == "/api/admin/session":
                    self.enforce_rate_limit(
                        bucket="login",
                        limit=LOGIN_RATE_LIMIT_MAX_REQUESTS,
                        message="Too many sign-in attempts. Please try again later.",
                    )
                    self.create_admin_session()
                elif path == "/api/admin/logout":
                    self.clear_admin_session()
                else:
                    if not self.require_admin_session():
                        return
                    self.enforce_rate_limit(
                        bucket="admin",
                        limit=ADMIN_RATE_LIMIT_MAX_REQUESTS,
                        message="Too many changes in a short time. Please wait a moment.",
                    )
                    self.update_admin_record()
            except ApiError as error:
                self.send_json(error.status, {"ok": False, "error": error.message})
            except StoreError:
                self.send_storage_error("The request could not be completed. Please try again.")
            return

        if path not in {"/api/service-requests", "/api/cleaner-availability"}:
            self.send_json(404, {"ok": False, "error": "That endpoint was not found."})
            return

        try:
            self.enforce_rate_limit()
            payload = self.read_json()
            if path == "/api/service-requests":
                reference, feedback_token = self.save_service_request(payload)
                message = "Your inquiry is saved and pending review. This is not a confirmed booking."
            else:
                reference = self.save_cleaner_availability(payload)
                message = "Your availability is saved and pending review. This is not a confirmed shift."
            result = {"ok": True, "reference": reference, "message": message}
            if path == "/api/service-requests":
                result["feedbackToken"] = feedback_token
            self.send_json(201, result)
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except StoreError:
            self.send_storage_error("The submission could not be saved. Please try again.")

    def save_service_request(self, payload):
        full_name = clean_text(payload.get("fullName"), "Name", 100)
        email = clean_email(payload.get("email"))
        area = clean_text(payload.get("area"), "Town or postal code", 100)
        service_type = clean_service_type(payload.get("serviceType"))
        preferred_date = clean_date(payload.get("preferredDate"), "Preferred date")
        preferred_time = clean_text(payload.get("preferredTime"), "Preferred time", 20).lower()
        if preferred_time not in PREFERRED_TIMES:
            raise ApiError(400, "Choose a listed preferred time.")
        notes = clean_text(
            payload.get("notes", ""),
            "Notes",
            800,
            required=False,
            allow_newlines=True,
        )
        consent = clean_consent(payload.get("consent"))
        reference = uuid.uuid4().hex[:12].upper()
        feedback_token = secrets.token_urlsafe(32)
        feedback_token_hash = hashlib.sha256(feedback_token.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()

        STORE.add_request(
            {
                "id": reference,
                "created_at": created_at,
                "full_name": full_name,
                "email": email,
                "area": area,
                "service_type": service_type,
                "preferred_date": preferred_date,
                "preferred_time": preferred_time,
                "notes": notes,
                "consent": consent,
                "status": "pending",
                "status_updated_at": created_at,
                "feedback_token_hash": feedback_token_hash,
            },
            {
                "record_type": "requests",
                "record_id": reference,
                "old_status": None,
                "new_status": "pending",
                "note": "Inquiry received.",
                "actor": "system",
                "created_at": created_at,
            },
        )
        return reference, feedback_token

    def handle_customer_feedback(self, payload):
        action = clean_text(payload.get("action"), "Feedback action", 20).lower()
        if action not in {"lookup", "review", "issue"}:
            raise ApiError(400, "Choose a valid feedback action.")

        token = payload.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ApiError(404, "That private feedback link is invalid.")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        request = STORE.find_request_by_token_hash(token_hash)
        if request is None:
            raise ApiError(404, "That private feedback link is invalid.")

        review_exists = STORE.get_review_for_request(request["id"]) is not None
        issue = STORE.get_issue_for_request(request["id"])
        issue_exists = issue is not None

        if action == "lookup":
            return 200, {
                "ok": True,
                "ready": request["status"] == "completed",
                "status": request["status"],
                "serviceType": request["service_type"],
                "preferredDate": request["preferred_date"],
                "reviewSubmitted": review_exists,
                "issueSubmitted": issue_exists,
                "issueStatus": issue["status"] if issue else None,
            }

        if request["status"] != "completed":
            raise ApiError(
                409,
                "Feedback is available after AdenClean marks the service complete.",
            )

        consent = clean_consent(payload.get("consent"))
        message = clean_text(
            payload.get("message"),
            "Feedback",
            1200,
            allow_newlines=True,
        )
        if len(message) < 10:
            raise ApiError(400, "Feedback must be at least 10 characters.")

        created_at = datetime.now(timezone.utc).isoformat()
        record_id = uuid.uuid4().hex[:12].upper()
        if action == "review":
            if review_exists:
                raise ApiError(409, "A review has already been submitted for this service.")
            rating = payload.get("rating")
            if isinstance(rating, bool) or not isinstance(rating, int) or rating not in range(1, 6):
                raise ApiError(400, "Choose a rating from 1 to 5.")
            record_status = "new"
            history_type = "reviews"
            history_note = "Customer review received."
            response_message = "Your review was saved for AdenClean to read."
            try:
                STORE.add_review(
                    {
                        "id": record_id,
                        "request_id": request["id"],
                        "created_at": created_at,
                        "rating": rating,
                        "message": message,
                        "consent": consent,
                        "status": "new",
                        "status_updated_at": created_at,
                    },
                    self.feedback_history(history_type, record_id, record_status, history_note, created_at),
                )
            except Conflict as error:
                raise ApiError(409, "A review has already been submitted for this service.") from error
        else:
            if issue_exists:
                raise ApiError(409, "A service issue has already been reported for this request.")
            record_status = "open"
            history_type = "issues"
            history_note = "Customer service issue reported."
            response_message = "Your service issue was sent to AdenClean for review."
            try:
                STORE.add_issue(
                    {
                        "id": record_id,
                        "request_id": request["id"],
                        "created_at": created_at,
                        "message": message,
                        "consent": consent,
                        "status": "open",
                        "status_updated_at": created_at,
                    },
                    self.feedback_history(history_type, record_id, record_status, history_note, created_at),
                )
            except Conflict as error:
                raise ApiError(409, "A service issue has already been reported for this request.") from error

        return 201, {
            "ok": True,
            "kind": action,
            "reference": record_id,
            "message": response_message,
            "reviewSubmitted": review_exists or action == "review",
            "issueSubmitted": issue_exists or action == "issue",
        }

    @staticmethod
    def feedback_history(record_type, record_id, status, note, created_at):
        return {
            "record_type": record_type,
            "record_id": record_id,
            "old_status": None,
            "new_status": status,
            "note": note,
            "actor": "customer",
            "created_at": created_at,
        }

    def save_cleaner_availability(self, payload):
        full_name = clean_text(payload.get("fullName"), "Name", 100)
        email = clean_email(payload.get("email"))
        area = clean_text(payload.get("area"), "Town or postal code", 100)
        service_types = payload.get("serviceTypes")
        if not isinstance(service_types, list) or not service_types or len(service_types) > 3:
            raise ApiError(400, "Choose at least one listed service type.")
        cleaned_service_types = sorted({clean_service_type(value) for value in service_types})
        available_date = clean_date(payload.get("availableDate"), "Available date")
        start_time = clean_time(payload.get("startTime"), "Start time")
        end_time = clean_time(payload.get("endTime"), "End time")
        if end_time <= start_time:
            raise ApiError(400, "End time must be later than start time.")
        consent = clean_consent(payload.get("consent"))
        reference = uuid.uuid4().hex[:12].upper()
        created_at = datetime.now(timezone.utc).isoformat()

        STORE.add_availability(
            {
                "id": reference,
                "created_at": created_at,
                "full_name": full_name,
                "email": email,
                "area": area,
                "service_types": json.dumps(cleaned_service_types),
                "available_date": available_date,
                "start_time": start_time,
                "end_time": end_time,
                "consent": consent,
                "status": "pending",
                "status_updated_at": created_at,
            },
            {
                "record_type": "availability",
                "record_id": reference,
                "old_status": None,
                "new_status": "pending",
                "note": "Availability received.",
                "actor": "system",
                "created_at": created_at,
            },
        )
        return reference

    # -- admin authentication --------------------------------------------------

    def admin_setup_message(self):
        if not os.environ.get("SESSION_SECRET"):
            return "SESSION_SECRET is not available to the app. Add it to the app's secrets and restart."
        if not STORE.has_admins():
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

        admin = STORE.get_admin(admin_id)
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

        admin = STORE.get_admin_by_email(email.strip().lower())
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

        records, counts, histories = STORE.list_records(
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
            current_status = STORE.get_status(record_type, record_id)
        except NotFound as error:
            raise ApiError(404, "That record could not be found.") from error
        if current_status != expected_status:
            raise ApiError(409, "This record changed. Refresh the list and try again.")
        if new_status == current_status:
            raise ApiError(400, "Choose a different status.")
        if new_status not in STATUS_TRANSITIONS[record_type][current_status]:
            raise ApiError(400, "That status change is not allowed.")

        try:
            STORE.set_status(
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


def main():
    global STORE
    if not STATIC_DIR.is_dir():
        raise RuntimeError(f"Static site directory not found: {STATIC_DIR}")

    STORE = storage.open_store()
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("0.0.0.0", port), AdenCleanHandler)
    print(f"AdenClean is available on port {port} (storage: {STORE.name}).")
    if STORE.name == "sqlite":
        print("WARNING: using local SQLite. Set ADENCLEAN_STORAGE=appwrite before collecting real data.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AdenClean.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
