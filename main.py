import json
import hmac
import os
import re
import sqlite3
import time
import uuid
import hashlib
from contextlib import closing
from datetime import date, datetime, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DATABASE_PATH = DATA_DIR / "adenclean.sqlite3"
MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_MAX_REQUESTS = 10
ADMIN_SESSION_COOKIE = "adenclean_admin_session"
ADMIN_SESSION_SECONDS = 8 * 60 * 60
ADMIN_PASSWORD_MIN_LENGTH = 16
RATE_LIMITS = {}
SERVICE_TYPES = {
    "routine": "Routine home cleaning",
    "deep": "Deep cleaning",
    "move-in/move-out": "Move-in / move-out",
    "move-in-move-out": "Move-in / move-out",
    "move-in-out": "Move-in / move-out",
}
PREFERRED_TIMES = {"morning", "afternoon", "flexible"}
RECORD_TYPES = {"requests": "customer_requests", "availability": "cleaner_availability"}
RECORD_STATUSES = {
    "requests": {"pending", "approved", "declined", "completed", "cancelled"},
    "availability": {"pending", "approved", "declined"},
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
}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def initialize_database():
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)

    try:
        descriptor = os.open(
            DATABASE_PATH,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError:
        os.chmod(DATABASE_PATH, 0o600)
    else:
        os.close(descriptor)

    with closing(sqlite3.connect(DATABASE_PATH)) as connection, connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customer_requests (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                area TEXT NOT NULL,
                service_type TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                preferred_time TEXT NOT NULL,
                notes TEXT NOT NULL,
                consent INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                status_updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cleaner_availability (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL,
                area TEXT NOT NULL,
                service_types TEXT NOT NULL,
                available_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                consent INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                status_updated_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        for table_name in ("customer_requests", "cleaner_availability"):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")
            }
            if "status" not in columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
                )
            if "status_updated_at" not in columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN status_updated_at TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                f"""
                UPDATE {table_name}
                SET status_updated_at = created_at
                WHERE status_updated_at = ''
                """
            )


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


class AdenCleanHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
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

    def enforce_rate_limit(self):
        now = time.monotonic()
        for address, timestamps in list(RATE_LIMITS.items()):
            recent = [
                timestamp
                for timestamp in timestamps
                if now - timestamp < RATE_LIMIT_WINDOW_SECONDS
            ]
            if recent:
                RATE_LIMITS[address] = recent
            else:
                RATE_LIMITS.pop(address, None)

        client_address = self.client_address[0]
        recent_requests = [
            timestamp
            for timestamp in RATE_LIMITS.get(client_address, [])
            if now - timestamp < RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(recent_requests) >= RATE_LIMIT_MAX_REQUESTS:
            RATE_LIMITS[client_address] = recent_requests
            raise ApiError(429, "Too many submissions. Please try again later.")
        recent_requests.append(now)
        RATE_LIMITS[client_address] = recent_requests

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/admin/session":
            if not self.admin_secret_is_configured():
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "configured": False,
                        "authenticated": False,
                        "message": self.admin_setup_message(),
                    },
                )
            elif self.admin_session_is_valid():
                self.send_json(
                    200,
                    {"ok": True, "configured": True, "authenticated": True},
                )
            else:
                self.send_json(401, {"ok": False, "error": "Sign in to continue."})
            return

        if path == "/api/admin/records":
            if not self.require_admin_session():
                return
            self.list_admin_records()
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
        if path in {"/api/admin/session", "/api/admin/logout", "/api/admin/records"}:
            try:
                if path == "/api/admin/session":
                    self.enforce_rate_limit()
                    self.create_admin_session()
                elif path == "/api/admin/logout":
                    self.clear_admin_session()
                else:
                    if not self.require_admin_session():
                        return
                    self.enforce_rate_limit()
                    self.update_admin_record()
            except ApiError as error:
                self.send_json(error.status, {"ok": False, "error": error.message})
            except sqlite3.Error:
                self.send_json(
                    500,
                    {"ok": False, "error": "The request could not be completed. Please try again."},
                )
            return

        if path not in {"/api/service-requests", "/api/cleaner-availability"}:
            self.send_json(404, {"ok": False, "error": "That endpoint was not found."})
            return

        try:
            self.enforce_rate_limit()
            payload = self.read_json()
            if path == "/api/service-requests":
                reference = self.save_service_request(payload)
                message = "Your inquiry is saved and pending review. This is not a confirmed booking."
            else:
                reference = self.save_cleaner_availability(payload)
                message = "Your availability is saved and pending review. This is not a confirmed shift."
            self.send_json(
                201,
                {"ok": True, "reference": reference, "message": message},
            )
        except ApiError as error:
            self.send_json(error.status, {"ok": False, "error": error.message})
        except sqlite3.Error:
            self.send_json(500, {"ok": False, "error": "The submission could not be saved. Please try again."})

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

        with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
            created_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO customer_requests (
                    id, created_at, full_name, email, area, service_type,
                    preferred_date, preferred_time, notes, consent, status, status_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    reference,
                    created_at,
                    full_name,
                    email,
                    area,
                    service_type,
                    preferred_date,
                    preferred_time,
                    notes,
                    consent,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO status_history (
                    record_type, record_id, old_status, new_status, note, actor, created_at
                ) VALUES ('requests', ?, NULL, 'pending', 'Inquiry received.', 'system', ?)
                """,
                (reference, created_at),
            )
        return reference

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

        with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
            created_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO cleaner_availability (
                    id, created_at, full_name, email, area, service_types,
                    available_date, start_time, end_time, consent, status, status_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    reference,
                    created_at,
                    full_name,
                    email,
                    area,
                    json.dumps(cleaned_service_types),
                    available_date,
                    start_time,
                    end_time,
                    consent,
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO status_history (
                    record_type, record_id, old_status, new_status, note, actor, created_at
                ) VALUES ('availability', ?, NULL, 'pending', 'Availability received.', 'system', ?)
                """,
                (reference, created_at),
            )
        return reference

    def admin_secret_is_configured(self):
        admin_password = os.environ.get("ADENCLEAN_ADMIN_PASSWORD", "")
        return bool(
            len(admin_password) >= ADMIN_PASSWORD_MIN_LENGTH
            and os.environ.get("SESSION_SECRET")
        )

    def admin_setup_message(self):
        return (
            "Set ADENCLEAN_ADMIN_PASSWORD to a unique password with at least "
            f"{ADMIN_PASSWORD_MIN_LENGTH} characters."
        )

    def make_admin_session(self):
        expires_at = int(time.time()) + ADMIN_SESSION_SECONDS
        session_payload = f"{expires_at}.{uuid.uuid4().hex}"
        signature = hmac.new(
            os.environ["SESSION_SECRET"].encode("utf-8"),
            session_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{session_payload}.{signature}"

    def admin_session_is_valid(self):
        if not self.admin_secret_is_configured():
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            session = cookie.get(ADMIN_SESSION_COOKIE)
        except CookieError:
            return False
        if session is None:
            return False

        parts = session.value.split(".")
        if len(parts) != 3 or not parts[0].isdigit():
            return False
        expires_at, nonce, supplied_signature = parts
        if len(nonce) != 32 or int(expires_at) < int(time.time()):
            return False

        session_payload = f"{expires_at}.{nonce}"
        expected_signature = hmac.new(
            os.environ["SESSION_SECRET"].encode("utf-8"),
            session_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(supplied_signature, expected_signature)

    def require_admin_session(self):
        if not self.admin_secret_is_configured():
            self.send_json(
                503,
                {"ok": False, "error": self.admin_setup_message()},
            )
            return False
        if not self.admin_session_is_valid():
            self.send_json(401, {"ok": False, "error": "Sign in to continue."})
            return False
        return True

    def create_admin_session(self):
        if not self.admin_secret_is_configured():
            self.send_json(
                503,
                {"ok": False, "error": self.admin_setup_message()},
            )
            return

        payload = self.read_json()
        supplied_password = payload.get("password")
        if not isinstance(supplied_password, str) or not hmac.compare_digest(
            supplied_password, os.environ["ADENCLEAN_ADMIN_PASSWORD"]
        ):
            self.send_json(401, {"ok": False, "error": "The password is incorrect."})
            return

        cookie = (
            f"{ADMIN_SESSION_COOKIE}={self.make_admin_session()}; "
            f"Max-Age={ADMIN_SESSION_SECONDS}; Path=/api/admin; "
            "HttpOnly; Secure; SameSite=Strict"
        )
        self.send_json(
            200,
            {"ok": True, "authenticated": True},
            headers={"Set-Cookie": cookie},
        )

    def clear_admin_session(self):
        cookie = (
            f"{ADMIN_SESSION_COOKIE}=; Max-Age=0; Path=/api/admin; "
            "HttpOnly; Secure; SameSite=Strict"
        )
        self.send_json(
            200,
            {"ok": True},
            headers={"Set-Cookie": cookie},
        )

    def list_admin_records(self):
        if not self.admin_secret_is_configured():
            self.send_json(
                503,
                {"ok": False, "error": self.admin_setup_message()},
            )
            return

        query = urlsplit(self.path).query
        from urllib.parse import parse_qs

        parameters = parse_qs(query, keep_blank_values=True)
        record_type = parameters.get("type", ["requests"])[0]
        status_filter = parameters.get("status", ["all"])[0]
        if record_type not in RECORD_TYPES:
            self.send_json(400, {"ok": False, "error": "Choose a valid record type."})
            return
        if status_filter != "all" and status_filter not in RECORD_STATUSES[record_type]:
            self.send_json(400, {"ok": False, "error": "Choose a valid status filter."})
            return

        table_name = RECORD_TYPES[record_type]
        selected_columns = (
            "id, created_at, full_name, email, area, service_type, preferred_date, "
            "preferred_time, notes, status, status_updated_at"
            if record_type == "requests"
            else "id, created_at, full_name, email, area, service_types, available_date, "
            "start_time, end_time, status, status_updated_at"
        )
        query_sql = f"SELECT {selected_columns} FROM {table_name}"
        query_values = []
        if status_filter != "all":
            query_sql += " WHERE status = ?"
            query_values.append(status_filter)
        query_sql += " ORDER BY created_at DESC LIMIT 100"

        with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            records = [
                dict(row)
                for row in connection.execute(query_sql, query_values).fetchall()
            ]
            counts = {
                status: 0 for status in RECORD_STATUSES[record_type]
            }
            for row in connection.execute(
                f"SELECT status, COUNT(*) AS total FROM {table_name} GROUP BY status"
            ):
                if row["status"] in counts:
                    counts[row["status"]] = row["total"]

            record_ids = [record["id"] for record in records]
            histories = {record_id: [] for record_id in record_ids}
            if record_ids:
                placeholders = ",".join("?" for _ in record_ids)
                for row in connection.execute(
                    f"""
                    SELECT record_id, old_status, new_status, note, actor, created_at
                    FROM status_history
                    WHERE record_type = ? AND record_id IN ({placeholders})
                    ORDER BY created_at ASC, id ASC
                    """,
                    [record_type, *record_ids],
                ):
                    histories[row["record_id"]].append(
                        {
                            "oldStatus": row["old_status"],
                            "newStatus": row["new_status"],
                            "note": row["note"],
                            "actor": row["actor"],
                            "createdAt": row["created_at"],
                        }
                    )

        for record in records:
            record["history"] = histories[record["id"]]
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
        table_name = RECORD_TYPES[record_type]
        changed_at = datetime.now(timezone.utc).isoformat()

        with closing(sqlite3.connect(DATABASE_PATH, timeout=10)) as connection, connection:
            current = connection.execute(
                f"SELECT status FROM {table_name} WHERE id = ?",
                (record_id,),
            ).fetchone()
            if current is None:
                raise ApiError(404, "That record could not be found.")
            current_status = current[0]
            if current_status != expected_status:
                raise ApiError(409, "This record changed. Refresh the list and try again.")
            if new_status == current_status:
                raise ApiError(400, "Choose a different status.")
            if new_status not in STATUS_TRANSITIONS[record_type][current_status]:
                raise ApiError(400, "That status change is not allowed.")

            updated = connection.execute(
                f"""
                UPDATE {table_name}
                SET status = ?, status_updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (new_status, changed_at, record_id, current_status),
            )
            if updated.rowcount != 1:
                raise ApiError(409, "This record changed. Refresh the list and try again.")
            connection.execute(
                """
                INSERT INTO status_history (
                    record_type, record_id, old_status, new_status, note, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, 'admin', ?)
                """,
                (record_type, record_id, current_status, new_status, note, changed_at),
            )

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
    if not STATIC_DIR.is_dir():
        raise RuntimeError(f"Static site directory not found: {STATIC_DIR}")

    initialize_database()
    server = ThreadingHTTPServer(("0.0.0.0", 5000), AdenCleanHandler)
    print("AdenClean is available on port 5000.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down AdenClean.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
