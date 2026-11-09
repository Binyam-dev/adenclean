"""AdenClean web server: static site, JSON API and request plumbing.

Endpoint logic lives in submissions.py (public forms), admin_routes.py (admin) and
api_v1.py (marketplace, off unless MARKETPLACE_ENABLED=1);
input validation lives in validation.py.
"""

import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import store as storage
from admin_routes import AdminRoutes
from api_v1 import MarketplaceRoutes
from store import StoreError
from submissions import SubmissionRoutes
from validation import ApiError


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_MAX_REQUESTS = 10
ADMIN_RATE_LIMIT_MAX_REQUESTS = 120
LOGIN_RATE_LIMIT_MAX_REQUESTS = 10
# Read-only status checks from the app. The app keeps up to 60 requests (MAX_SAVED in
# mobile/src/lib/storage.ts) and reuses an answer for 5 minutes (mobile/src/lib/lookup-cache.ts),
# so one 15-minute window can hold three automatic full-list checks plus a pull-to-refresh.
APP_MAX_SAVED_REQUESTS = 60
LOOKUP_RATE_LIMIT_MAX_REQUESTS = 4 * APP_MAX_SAVED_REQUESTS
RATE_LIMITS = {}
STORE = None
RATE_LIMIT_LOCK = threading.Lock()
DEFAULT_PORT = 5000


ADMIN_ALIASES = ("vetting", "moderation")  # /api/admin/<name> -> /api/v1/admin/<name>
ASSET_TYPES = {"png", "jpg", "jpeg", "svg", "ico", "ttf", "woff", "woff2"}


def cache_policy(request_path):
    """Cache-Control for a response. API replies are never stored. Pages, CSS and JS are
    revalidated on every use (a 304 when unchanged), so a deploy shows up at once and the
    browser's back/forward cache still works. Images and fonts, which change rarely, may be
    reused for a day."""
    path = urlsplit(request_path).path
    if path.startswith("/api/"):
        return "no-store"
    extension = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return "public, max-age=86400" if extension in ASSET_TYPES else "no-cache"


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


class AdenCleanHandler(MarketplaceRoutes, SubmissionRoutes, AdminRoutes, SimpleHTTPRequestHandler):
    # Drop clients that stall mid-request instead of holding a thread forever.
    timeout = 30

    @property
    def store(self):
        return STORE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def discard_unread_body(self):
        """Read a request body nobody consumed (early 401/404/415/429 replies).

        Closing a socket with unread data makes the OS send a TCP reset, so the client
        sees "connection reset" instead of our error message (always on Windows, and
        sometimes through proxies). Oversized bodies are not read; the connection closes.
        """
        if getattr(self, "_body_read_for", None) is self.headers:
            return
        self._body_read_for = self.headers
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if 0 < length <= MAX_BODY_BYTES:
            self.rfile.read(length)

    def end_headers(self):
        if proxy_hops():  # served over HTTPS by the proxy
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Cache-Control", cache_policy(self.path))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        dev_origin = os.environ.get("ADENCLEAN_DEV_CORS_ORIGIN", "")
        # Local development only (Expo web on another port). Never set this in production.
        if dev_origin.startswith("http://localhost:") and self.headers.get("Origin") == dev_origin:
            self.send_header("Access-Control-Allow-Origin", dev_origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204 if os.environ.get("ADENCLEAN_DEV_CORS_ORIGIN") else 405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, status, payload, headers=None):
        self.discard_unread_body()
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

        self._body_read_for = self.headers
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

    def admin_alias(self, path, method):
        """The admin session cookie is only sent under /api/admin, so these review endpoints
        are reachable there too: same handlers, same admin-session check. Returns True if handled."""
        for name in ADMIN_ALIASES:
            prefix = f"/api/admin/{name}"
            if path == prefix or path.startswith(prefix + "/"):
                self.path = f"/api/v1/admin/{name}" + self.path[len(prefix):]
                self.handle_v1(method)
                return True
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/index.html":  # one address per page, so search engines see one copy
            self.send_response(301)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path.startswith("/api/v1/"):
            self.handle_v1("GET")
            return
        if self.admin_alias(path, "GET"):
            return
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
        if path.startswith("/api/v1/"):
            self.handle_v1("POST")
            return
        if self.admin_alias(path, "POST"):
            return
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
