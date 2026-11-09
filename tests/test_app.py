"""End-to-end tests: a real HTTP server, run against both storage backends."""

import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402
import main  # noqa: E402
import store as storage  # noqa: E402

try:
    from fake_appwrite import FakeTablesDB
    HAVE_APPWRITE = True
except ImportError:
    HAVE_APPWRITE = False

PASSWORD = "correct horse battery"
EMAIL = "owner@example.com"


class AppCase:
    def setUp(self):
        os.environ["SESSION_SECRET"] = "x" * 48
        main.RATE_LIMITS.clear()
        main.STORE = self.make_store()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.AdenCleanHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    # -- helpers ---------------------------------------------------------------

    def call(self, method, path, payload=None, cookie=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if cookie:
            headers["Cookie"] = cookie
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}"), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}"), error.headers

    def add_admin(self, email=EMAIL, password=PASSWORD, active=1):
        admin_id = os.urandom(16).hex()
        main.STORE.add_admin({
            "id": admin_id, "email": email, "password_hash": auth.hash_password(password),
            "role": "admin", "active": active, "created_at": "2026-11-01T00:00:00+00:00",
        })
        return admin_id

    def sign_in(self, email=EMAIL, password=PASSWORD):
        status, body, headers = self.call("POST", "/api/admin/session", {"email": email, "password": password})
        self.assertEqual(status, 200, body)
        return headers["Set-Cookie"].split(";")[0]

    def submit_request(self):
        status, body, _ = self.call("POST", "/api/service-requests", {
            "fullName": "Pat Customer", "email": "pat@example.com", "area": "Silver Spring",
            "serviceType": "routine", "preferredDate": (date.today() + timedelta(days=3)).isoformat(),
            "preferredTime": "morning", "notes": "Two cats", "consent": True,
        })
        self.assertEqual(status, 201, body)
        return body["reference"], body["feedbackToken"]

    def change_status(self, cookie, reference, expected, new, record_type="requests"):
        return self.call("POST", "/api/admin/records", {
            "type": record_type, "id": reference, "status": new, "expectedStatus": expected, "note": "ok",
        }, cookie)

    # -- tests -----------------------------------------------------------------

    def test_public_privacy_notice_says_where_submissions_are_stored(self):
        # This notice is linked before consent and must be readable without an admin session.
        with urllib.request.urlopen(self.base + "/policies.html", timeout=10) as response:
            self.assertEqual(response.status, 200)
            notice = response.read().decode("utf-8")
        self.assertIn("Appwrite", notice)
        self.assertNotIn("SQLite", notice)

    def test_admin_setup_message_until_first_admin_exists(self):
        status, body, _ = self.call("GET", "/api/admin/session")
        self.assertFalse(body["configured"])
        self.assertIn("create_admin.py", body["message"])
        self.add_admin()
        status, body, _ = self.call("GET", "/api/admin/session")
        self.assertTrue(body["configured"])
        self.assertFalse(body["authenticated"])

    def test_wrong_password_and_unknown_email_look_identical(self):
        self.add_admin()
        wrong = self.call("POST", "/api/admin/session", {"email": EMAIL, "password": "nope-nope-nope"})
        unknown = self.call("POST", "/api/admin/session", {"email": "who@example.com", "password": "nope-nope-nope"})
        self.assertEqual(wrong[0], 401)
        self.assertEqual(wrong[:2], unknown[:2])
        self.assertIn("incorrect", wrong[1]["error"])

    def test_old_shared_password_no_longer_works(self):
        os.environ["ADENCLEAN_ADMIN_PASSWORD"] = "old shared password"
        self.addCleanup(os.environ.pop, "ADENCLEAN_ADMIN_PASSWORD", None)
        self.add_admin()
        status, _, _ = self.call("POST", "/api/admin/session", {"password": "old shared password"})
        self.assertIn(status, (400, 401))

    def test_records_require_a_session(self):
        self.add_admin()
        self.assertEqual(self.call("GET", "/api/admin/records")[0], 401)
        self.assertEqual(self.change_status(None, "X", "pending", "approved")[0], 401)

    def test_tampered_and_forged_cookies_are_rejected(self):
        admin_id = self.add_admin()
        cookie = self.sign_in()
        name, value = cookie.split("=", 1)
        parts = value.split(".")
        tampered = f"{name}={parts[0]}.{'f' * 32}.{parts[2]}.{parts[3]}"  # other admin id, same signature
        self.assertEqual(self.call("GET", "/api/admin/records", cookie=tampered)[0], 401)
        forged = f"{name}=9999999999.{admin_id}.{'0' * 32}.{'0' * 64}"
        self.assertEqual(self.call("GET", "/api/admin/records", cookie=forged)[0], 401)
        self.assertEqual(self.call("GET", "/api/admin/records", cookie=cookie)[0], 200)

    def test_disabling_an_admin_ends_their_session(self):
        self.add_admin()
        cookie = self.sign_in()
        self.assertEqual(self.call("GET", "/api/admin/records", cookie=cookie)[0], 200)
        main.STORE.set_admin_active(EMAIL, False)
        self.assertEqual(self.call("GET", "/api/admin/records", cookie=cookie)[0], 401)
        status, _, _ = self.call("POST", "/api/admin/session", {"email": EMAIL, "password": PASSWORD})
        self.assertEqual(status, 401)

    def test_full_customer_and_admin_flow(self):
        self.add_admin()
        self.add_admin("second@example.com", "another long password")
        reference, token = self.submit_request()

        status, lookup, _ = self.call("POST", "/api/customer-feedback", {"action": "lookup", "token": token})
        self.assertEqual((status, lookup["ready"]), (200, False))
        too_early = self.call("POST", "/api/customer-feedback", {
            "action": "review", "token": token, "rating": 5, "message": "Great work today", "consent": True})
        self.assertEqual(too_early[0], 409)

        first = self.sign_in()
        second = self.sign_in("second@example.com", "another long password")
        self.assertEqual(self.change_status(first, reference, "pending", "approved")[0], 200)
        self.assertEqual(self.change_status(first, reference, "pending", "approved")[0], 409)  # stale
        self.assertEqual(self.change_status(second, reference, "approved", "pending")[0], 200)
        self.assertEqual(self.change_status(second, reference, "pending", "completed")[0], 400)  # not allowed
        self.assertEqual(self.change_status(first, reference, "pending", "approved")[0], 200)
        self.assertEqual(self.change_status(first, reference, "approved", "completed")[0], 200)
        self.assertEqual(self.change_status(first, "NOSUCHREF000", "pending", "approved")[0], 404)

        status, body, _ = self.call("GET", "/api/admin/records?type=requests", cookie=first)
        record = body["records"][0]
        self.assertEqual(record["status"], "completed")
        self.assertNotIn("feedback_token_hash", record)
        actors = [entry["actor"] for entry in record["history"]]
        self.assertEqual(actors[0], "system")
        self.assertIn("second@example.com", actors)
        self.assertIn(EMAIL, actors)
        self.assertEqual(body["counts"]["completed"], 1)

        review = {"action": "review", "token": token, "rating": 4, "message": "Spotless kitchen", "consent": True}
        self.assertEqual(self.call("POST", "/api/customer-feedback", review)[0], 201)
        self.assertEqual(self.call("POST", "/api/customer-feedback", review)[0], 409)
        issue = {"action": "issue", "token": token, "message": "A mug was chipped", "consent": True}
        self.assertEqual(self.call("POST", "/api/customer-feedback", issue)[0], 201)
        self.assertEqual(self.call("POST", "/api/customer-feedback", issue)[0], 409)

        status, lookup, _ = self.call("POST", "/api/customer-feedback", {"action": "lookup", "token": token})
        self.assertTrue(lookup["ready"] and lookup["reviewSubmitted"] and lookup["issueSubmitted"])
        self.assertEqual(lookup["issueStatus"], "open")

        status, reviews, _ = self.call("GET", "/api/admin/records?type=reviews", cookie=first)
        self.assertEqual(reviews["records"][0]["full_name"], "Pat Customer")
        status, issues, _ = self.call("GET", "/api/admin/records?type=issues&status=open", cookie=first)
        self.assertEqual(len(issues["records"]), 1)

    def test_health_check_needs_no_sign_in_and_hides_details(self):
        status, body, _ = self.call("GET", "/healthz")
        self.assertEqual((status, body), (200, {"ok": True}))

    def test_rate_limit_separates_clients_behind_a_proxy(self):
        os.environ["ADENCLEAN_PROXY_HOPS"] = "1"
        self.addCleanup(os.environ.pop, "ADENCLEAN_PROXY_HOPS", None)

        def post(client):
            request = urllib.request.Request(
                self.base + "/api/customer-feedback", method="POST",
                data=b'{"action": "review", "token": "short"}',
                headers={"Content-Type": "application/json", "X-Forwarded-For": f"9.9.9.9, {client}"},
            )
            try:
                return urllib.request.urlopen(request, timeout=10).status
            except urllib.error.HTTPError as error:
                return error.code

        codes = [post("203.0.113.1") for _ in range(main.RATE_LIMIT_MAX_REQUESTS + 1)]
        self.assertEqual(codes[-1], 429)  # the first client ran out...
        self.assertEqual(post("203.0.113.2"), 404)  # ...a different client behind the same proxy did not

    def test_status_checks_have_their_own_larger_allowance(self):
        lookup = {"action": "lookup", "token": "short"}
        codes = [
            self.call("POST", "/api/customer-feedback", lookup)[0]
            for _ in range(main.RATE_LIMIT_MAX_REQUESTS + 15)
        ]
        self.assertNotIn(429, codes)  # more than the submission limit, still allowed
        # ...and using it up does not block sending a request
        self.assertEqual(self.submit_request()[0] != "", True)
        # a flood of lookups is still cut off
        flood = [
            self.call("POST", "/api/customer-feedback", lookup)[0]
            for _ in range(main.LOOKUP_RATE_LIMIT_MAX_REQUESTS)
        ]
        self.assertIn(429, flood)

    def test_status_allowance_covers_the_apps_saved_list(self):
        # The app looks up every saved request on its Requests tab; the allowance has to
        # cover several full lists in one window or normal use hits 429s.
        storage = (Path(main.ROOT) / "mobile" / "src" / "lib" / "storage.ts").read_text()
        match = re.search(r"const MAX_SAVED = (\d+);", storage)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), main.APP_MAX_SAVED_REQUESTS)
        self.assertGreaterEqual(main.LOOKUP_RATE_LIMIT_MAX_REQUESTS, 3 * main.APP_MAX_SAVED_REQUESTS)

    def test_bad_feedback_tokens_are_not_found(self):
        for token in ("short", "A" * 43, None):
            status, _, _ = self.call("POST", "/api/customer-feedback", {"action": "lookup", "token": token})
            self.assertEqual(status, 404)

    def test_cleaner_availability_is_saved_and_listed(self):
        self.add_admin()
        status, body, _ = self.call("POST", "/api/cleaner-availability", {
            "fullName": "Sam Cleaner", "email": "sam@example.com", "area": "Takoma Park",
            "serviceTypes": ["routine", "deep"], "availableDate": (date.today() + timedelta(days=2)).isoformat(),
            "startTime": "09:00", "endTime": "13:00", "consent": True,
        })
        self.assertEqual(status, 201, body)
        cookie = self.sign_in()
        status, listing, _ = self.call("GET", "/api/admin/records?type=availability", cookie=cookie)
        self.assertEqual(listing["records"][0]["full_name"], "Sam Cleaner")

    def test_submission_validation_still_applies(self):
        status, body, _ = self.call("POST", "/api/service-requests", {"fullName": "", "consent": True})
        self.assertEqual(status, 400)
        status, body, _ = self.call("POST", "/api/service-requests", {
            "fullName": "A", "email": "a@example.com", "area": "x", "serviceType": "routine",
            "preferredDate": (date.today() + timedelta(days=1)).isoformat(),
            "preferredTime": "morning", "consent": False,
        })
        self.assertEqual(status, 400)

    def test_sign_in_attempts_are_rate_limited(self):
        self.add_admin()
        codes = [
            self.call("POST", "/api/admin/session", {"email": EMAIL, "password": "wrong-wrong-wrong"})[0]
            for _ in range(main.LOGIN_RATE_LIMIT_MAX_REQUESTS + 2)
        ]
        self.assertEqual(codes[:main.LOGIN_RATE_LIMIT_MAX_REQUESTS], [401] * main.LOGIN_RATE_LIMIT_MAX_REQUESTS)
        self.assertEqual(codes[-1], 429)
        # ...and signing in is a separate allowance from public form submissions
        self.assertEqual(self.submit_request()[0] != "", True)

    def test_storage_failure_returns_a_generic_error(self):
        self.add_admin()

        def broken(*_args, **_kwargs):
            raise storage.StoreError("boom with details")
        main.STORE.add_request = broken
        status, body, _ = self.call("POST", "/api/service-requests", {
            "fullName": "Pat", "email": "pat@example.com", "area": "Silver Spring",
            "serviceType": "routine", "preferredDate": (date.today() + timedelta(days=3)).isoformat(),
            "preferredTime": "morning", "consent": True,
        })
        self.assertEqual(status, 500)
        self.assertNotIn("boom", json.dumps(body))


class DeploymentTests(unittest.TestCase):
    def test_client_address_ignores_spoofed_forwarding_headers(self):
        # one trusted proxy: it appends the address it saw, so take the rightmost entry
        self.assertEqual(main.client_address("10.0.0.1", "6.6.6.6, 203.0.113.9", 1), "203.0.113.9")
        # no proxy configured: headers are never trusted
        self.assertEqual(main.client_address("198.51.100.4", "6.6.6.6", 0), "198.51.100.4")
        # header shorter than the hop count: fall back to the socket address
        self.assertEqual(main.client_address("10.0.0.1", "203.0.113.9", 2), "10.0.0.1")
        self.assertEqual(main.client_address("10.0.0.1", "", 1), "10.0.0.1")

    def test_proxy_hops_setting_is_bounded_and_safe(self):
        self.assertEqual(main.proxy_hops({}), 0)
        self.assertEqual(main.proxy_hops({"ADENCLEAN_PROXY_HOPS": "1"}), 1)
        self.assertEqual(main.proxy_hops({"ADENCLEAN_PROXY_HOPS": "99"}), 5)
        self.assertEqual(main.proxy_hops({"ADENCLEAN_PROXY_HOPS": "-3"}), 0)
        self.assertEqual(main.proxy_hops({"ADENCLEAN_PROXY_HOPS": "x"}), 0)


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwriteAppTests(AppCase, unittest.TestCase):
    def make_store(self):
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean",
                                     tables_db=FakeTablesDB())


if __name__ == "__main__":
    unittest.main()

