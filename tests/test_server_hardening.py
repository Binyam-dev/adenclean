"""Consistent 500 answers, health checks, security headers, and log hygiene."""

import io
import json
import logging
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
import observability  # noqa: E402
import store as storage  # noqa: E402

TOKEN = "A" * 43  # right shape for a private link code, matches nothing


class ExplodingStore:
    """A store whose reads crash with a bug-like error, to prove the server still answers."""
    name = "memory"

    def find_request_by_token_hash(self, _hash):
        raise RuntimeError("secret internal detail: db password hunter2")

    def has_admins(self):
        raise storage.StoreError("down")


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.original_store = main.STORE
        main.STORE = storage.open_store({"ADENCLEAN_STORAGE": "memory"})
        main.RATE_LIMITS.clear()
        self.addCleanup(setattr, main, "STORE", self.original_store)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.AdenCleanHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.captured = io.StringIO()
        handler = logging.StreamHandler(self.captured)
        handler.setFormatter(observability.JsonFormatter())
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def open(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def log_lines(self):
        return [json.loads(line) for line in self.captured.getvalue().splitlines() if line.startswith("{")]

    # -- errors ---------------------------------------------------------------------------

    def test_an_unexpected_crash_still_returns_json_without_details(self):
        main.STORE = ExplodingStore()
        status, headers, body = self.open("/api/customer-feedback", {"action": "lookup", "token": TOKEN})
        self.assertEqual(status, 500)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        payload = json.loads(body)
        self.assertEqual(payload, {"ok": False, "error": main.SERVER_ERROR_MESSAGE})
        self.assertNotIn(b"hunter2", body)
        self.assertRegex(headers["X-Request-Id"], r"^[0-9a-f]{12}$")
        errors = [line for line in self.log_lines() if line["msg"] == "unhandled error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["rid"], headers["X-Request-Id"])

    def test_the_server_keeps_working_after_a_crash(self):
        main.STORE = ExplodingStore()
        self.open("/api/customer-feedback", {"action": "lookup", "token": TOKEN})
        main.STORE = storage.open_store({"ADENCLEAN_STORAGE": "memory"})
        self.assertEqual(self.open("/healthz")[0], 200)

    def test_known_errors_keep_their_own_messages(self):
        status, _, body = self.open("/api/service-requests", {"fullName": ""})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["ok"], False)
        status, _, body = self.open("/api/customer-feedback", {"action": "lookup", "token": "short"})
        self.assertEqual((status, json.loads(body)["error"]), (404, "That private feedback link is invalid."))

    # -- health ---------------------------------------------------------------------------

    def test_health_endpoints(self):
        status, _, body = self.open("/healthz")
        self.assertEqual((status, json.loads(body)["ok"]), (200, True))
        status, _, body = self.open("/health")
        payload = json.loads(body)
        self.assertEqual((status, payload["storage"]), (200, "memory"))
        self.assertIn("release", payload)
        status, _, body = self.open("/health?deep=1")
        self.assertEqual((status, json.loads(body)["database"]), (200, "ok"))

    def test_deep_health_fails_loudly_when_storage_is_down(self):
        main.STORE = ExplodingStore()
        status, _, body = self.open("/health?deep=1")
        self.assertEqual((status, json.loads(body)["database"]), (503, "unreachable"))
        self.assertEqual(self.open("/healthz")[0], 200)  # the plain check only proves the process is up

    def test_health_reveals_no_secrets(self):
        _, _, body = self.open("/health?deep=1")
        text = body.decode()
        for word in ("key", "secret", "password", "endpoint", "project"):
            self.assertNotIn(word, text.lower())

    # -- headers --------------------------------------------------------------------------

    def test_security_headers_on_pages_and_api(self):
        for path in ("/", "/policies.html", "/api/admin/session", "/healthz"):
            with self.subTest(path=path):
                _, headers, _ = self.open(path, method="HEAD" if path.endswith((".html", "/")) else None)
                self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
                self.assertEqual(headers["X-Frame-Options"], "DENY")
                self.assertIn("geolocation=()", headers["Permissions-Policy"])
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertTrue(headers["X-Request-Id"])

    def test_pages_work_under_the_content_security_policy(self):
        """The policy blocks inline scripts and styles, so no page may use them."""
        for page in ("index.html", "admin.html", "feedback.html", "policies.html"):
            html = (ROOT / "static" / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>")
                self.assertNotIn("<style", html)
                self.assertNotRegex(html, r"\sstyle=")
                self.assertNotRegex(html, r"\son[a-z]+=")
                for url in re.findall(r'(?:src|href)="(https?://[^"]+)"', html):
                    self.assertTrue(url.startswith("https://adenclean.onrender.com"), url)
        for script in (ROOT / "static").glob("*.js"):
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"setAttribute\(\s*['\"]style['\"]")
                self.assertNotIn("eval(", text)

    def test_folders_are_never_listed_and_paths_cannot_escape_the_site(self):
        folder = ROOT / "static" / "probe-folder"
        folder.mkdir(exist_ok=True)
        (folder / "inside.txt").write_text("x", encoding="utf-8")
        self.addCleanup(lambda: (folder / "inside.txt").unlink() or folder.rmdir())
        for path in ("/probe-folder/", "/probe-folder"):
            with self.subTest(path=path):
                status, _, body = self.open(path)
                self.assertNotIn(b"inside.txt", body)
                self.assertIn(status, (301, 404))
        self.assertEqual(self.open("/probe-folder/inside.txt")[0], 200)  # a file you name still works
        for path in ("/../main.py", "/%2e%2e/main.py", "/..%2fmain.py", "/static/../main.py"):
            with self.subTest(path=path):
                status, _, body = self.open(path)
                self.assertNotIn(b"AdenCleanHandler", body)

    # -- logs -----------------------------------------------------------------------------

    def test_logs_are_json_and_never_hold_query_strings_bodies_or_codes(self):
        self.open("/robots.txt?utm_source=SECRETQUERY")  # a small file: big local downloads can stall on Windows
        self.open("/api/customer-feedback", {"action": "lookup", "token": TOKEN})
        self.open("/api/service-requests", {"fullName": "Pat Private", "email": "pat.private@example.com"})
        requests = [line for line in self.log_lines() if line["msg"] == "request"]
        self.assertGreaterEqual(len(requests), 3)
        for line in requests:
            self.assertEqual(set(line) - {"ts", "level", "logger", "msg"}, {"rid", "method", "path", "status", "ms", "ip"})
        everything = self.captured.getvalue()
        for private in ("SECRETQUERY", TOKEN, "Pat Private", "pat.private@example.com"):
            self.assertNotIn(private, everything)


class ObservabilityTests(unittest.TestCase):
    def test_monitoring_is_off_without_a_dsn(self):
        stream = io.StringIO()
        self.assertFalse(observability.configure({}, stream=stream))
        logging.getLogger("adenclean.test").info("hello", extra={"fields": {"n": 1}})
        entry = json.loads(stream.getvalue().strip().splitlines()[-1])
        self.assertEqual((entry["msg"], entry["n"], entry["level"]), ("hello", 1, "info"))

    def test_release_comes_from_settings_then_render_then_dev(self):
        self.assertEqual(observability.release({"ADENCLEAN_RELEASE": "abc123"}), "abc123")
        self.assertEqual(observability.release({"RENDER_GIT_COMMIT": "deadbeef"}), "deadbeef")
        self.assertEqual(observability.release({}), "dev")

    def test_reporting_an_error_is_safe_when_monitoring_is_off(self):
        observability.capture(RuntimeError("x"), "rid", "/p")  # must not raise


if __name__ == "__main__":
    unittest.main()
