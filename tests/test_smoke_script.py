"""The smoke-test script itself, run against an in-process server with an admin account."""

import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auth  # noqa: E402
import main  # noqa: E402
import smoke_test  # noqa: E402
import store as storage  # noqa: E402

PASSWORD = "a long smoke password"


class SmokeScriptTests(unittest.TestCase):
    def setUp(self):
        self.original = main.STORE
        main.STORE = storage.open_store({"ADENCLEAN_STORAGE": "memory"})
        main.RATE_LIMITS.clear()
        self.addCleanup(setattr, main, "STORE", self.original)
        main.STORE.add_admin({"id": "a" * 32, "email": "ops@example.com", "password_hash": auth.hash_password(PASSWORD),
                              "role": "admin", "active": 1, "created_at": "2026-11-09T00:00:00+00:00"})
        import os
        os.environ["SESSION_SECRET"] = "x" * 48
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.AdenCleanHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.lines = []

    def test_every_customer_and_admin_step_passes(self):
        ok = smoke_test.run(self.base, "ops@example.com", PASSWORD, out=self.lines.append)
        self.assertTrue(ok, "\n".join(self.lines))
        self.assertFalse([line for line in self.lines if line.startswith("FAIL")])
        for expected in ("flow 1", "flow 2", "flow 3: a review is saved", "flow 3: an issue report is saved",
                         "admin: assign", "admin: mark complete", "admin: moderate the review", "admin: moderate the issue"):
            self.assertTrue(any(expected in line for line in self.lines), expected)

    def test_without_an_admin_login_it_stops_at_the_customer_flows_and_says_so(self):
        ok = smoke_test.run(self.base, out=self.lines.append)
        self.assertTrue(ok)
        self.assertTrue(any(line.startswith("NOTE") for line in self.lines))
        self.assertFalse(any("admin:" in line for line in self.lines))

    def test_a_wrong_admin_password_fails_the_run(self):
        self.assertFalse(smoke_test.run(self.base, "ops@example.com", "wrong password here", out=self.lines.append))

    def test_a_sign_out_that_does_not_clear_the_session_fails_the_run(self):
        original = main.AdenCleanHandler.clear_admin_session

        def broken_logout(handler):
            handler.send_json(200, {"ok": True})  # answers, but leaves the session cookie in place

        main.AdenCleanHandler.clear_admin_session = broken_logout
        self.addCleanup(setattr, main.AdenCleanHandler, "clear_admin_session", original)
        self.assertFalse(smoke_test.run(self.base, "ops@example.com", PASSWORD, out=self.lines.append))
        self.assertTrue(any(line.startswith("FAIL") and "sign out" in line for line in self.lines), "\n".join(self.lines))

    def test_the_output_never_holds_a_private_code_or_password(self):
        smoke_test.run(self.base, "ops@example.com", PASSWORD, out=self.lines.append)
        text = "\n".join(self.lines)
        self.assertNotIn(PASSWORD, text)
        import re
        self.assertIsNone(re.search(r"[A-Za-z0-9_-]{43}", text))


if __name__ == "__main__":
    unittest.main()
