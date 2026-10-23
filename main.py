import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
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
RATE_LIMITS = {}
SERVICE_TYPES = {
    "routine": "Routine home cleaning",
    "deep": "Deep cleaning",
    "move-in/move-out": "Move-in / move-out",
    "move-in-move-out": "Move-in / move-out",
    "move-in-out": "Move-in / move-out",
}
PREFERRED_TIMES = {"morning", "afternoon", "flexible"}


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
                consent INTEGER NOT NULL
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
                consent INTEGER NOT NULL
            );
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

    def send_json(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
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
        if urlsplit(self.path).path.startswith("/api/"):
            self.send_json(405, {"ok": False, "error": "This API only accepts submissions."})
            return
        super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in {"/api/service-requests", "/api/cleaner-availability"}:
            self.send_json(404, {"ok": False, "error": "That endpoint was not found."})
            return

        try:
            self.enforce_rate_limit()
            payload = self.read_json()
            if path == "/api/service-requests":
                reference = self.save_service_request(payload)
                message = "Your inquiry is saved. This is not a confirmed booking."
            else:
                reference = self.save_cleaner_availability(payload)
                message = "Your availability is saved. This is not a confirmed booking."
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
            connection.execute(
                """
                INSERT INTO customer_requests (
                    id, created_at, full_name, email, area, service_type,
                    preferred_date, preferred_time, notes, consent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference,
                    datetime.now(timezone.utc).isoformat(),
                    full_name,
                    email,
                    area,
                    service_type,
                    preferred_date,
                    preferred_time,
                    notes,
                    consent,
                ),
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
            connection.execute(
                """
                INSERT INTO cleaner_availability (
                    id, created_at, full_name, email, area, service_types,
                    available_date, start_time, end_time, consent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference,
                    datetime.now(timezone.utc).isoformat(),
                    full_name,
                    email,
                    area,
                    json.dumps(cleaned_service_types),
                    available_date,
                    start_time,
                    end_time,
                    consent,
                ),
            )
        return reference


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
