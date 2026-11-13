"""Push notifications: registering devices, sending on status changes, and never leaking a token."""

import io
import json
import logging
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
import main  # noqa: E402
import observability  # noqa: E402
import push  # noqa: E402
import store as storage  # noqa: E402

PASSWORD = "a long push password"
TOKEN_A = "ExponentPushToken[AAAAAAAAAAAAAAAAAAAAAA]"
TOKEN_B = "ExponentPushToken[BBBBBBBBBBBBBBBBBBBBBB]"
TOKEN_C = "ExponentPushToken[CCCCCCCCCCCCCCCCCCCCCC]"
TOKEN_D = "ExpoPushToken[DDDDDDDDDDDDDDDDDDDDDD]"
TOKENS = (TOKEN_A, TOKEN_B, TOKEN_C, TOKEN_D)
FIXED_BODY = "Update on your request. Tap for details."


class Fake:
    """A stand-in for Expo that records every call."""
    def __init__(self, errors=None):
        self.calls = []
        self.errors = errors or {}

    def __call__(self, messages):
        self.calls.append(messages)
        return [{"status": "error" if m["to"] in self.errors else "ok", "error": self.errors.get(m["to"])} for m in messages]


class PushCase(unittest.TestCase):
    def setUp(self):
        self.old_store, self.old_sender, self.old_env = main.STORE, push.SENDER, os.environ.get("PUSH_ENABLED")
        main.STORE = storage.open_store({"ADENCLEAN_STORAGE": "memory"})
        main.RATE_LIMITS.clear()
        main.STORE.add_admin({"id": "a" * 32, "email": "ops@example.com", "password_hash": auth.hash_password(PASSWORD),
                              "role": "admin", "active": 1, "created_at": "2026-11-13T00:00:00+00:00"})
        os.environ["SESSION_SECRET"] = "x" * 48
        os.environ["PUSH_ENABLED"] = "1"
        self.fake = push.SENDER = Fake()
        self.addCleanup(self.restore)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.AdenCleanHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.logs = io.StringIO()
        handler = logging.StreamHandler(self.logs)
        handler.setFormatter(observability.JsonFormatter())
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        self.cookie = None

    def restore(self):
        push.SENDER = self.old_sender
        main.STORE = self.old_store
        if self.old_env is None:
            os.environ.pop("PUSH_ENABLED", None)
        else:
            os.environ["PUSH_ENABLED"] = self.old_env

    # -- helpers --------------------------------------------------------------------------

    def call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"{}"), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}"), error.headers

    def new_request(self):
        status, body, _ = self.call("POST", "/api/service-requests", {
            "fullName": "Pat Private", "email": "pat.private@example.com", "area": "20910", "serviceType": "deep",
            "preferredDate": "2030-01-05", "preferredTime": "morning", "notes": "Two cats", "consent": True})
        self.assertEqual(status, 201, body)
        return body["reference"], body["feedbackToken"]

    def sign_in(self):
        status, _, headers = self.call("POST", "/api/admin/session", {"email": "ops@example.com", "password": PASSWORD})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";")[0]

    def register(self, code, token, action="push_register"):
        return self.call("POST", "/api/customer-feedback", {"action": action, "token": code, "pushToken": token})

    def set_status(self, reference, old, new):
        return self.call("POST", "/api/admin/records", {"type": "requests", "id": reference, "expectedStatus": old,
                                                       "status": new, "note": ""})

    def tokens(self, reference):
        return push.get_tokens(main.STORE, reference)

    # -- registering ----------------------------------------------------------------------

    def test_register_and_unregister_only_the_given_device(self):
        reference, code = self.new_request()
        self.assertEqual(self.register(code, TOKEN_A)[0], 200)
        self.assertEqual(self.register(code, TOKEN_B)[0], 200)
        self.assertEqual(self.register(code, TOKEN_A)[0], 200)  # repeating does not duplicate
        self.assertEqual(self.tokens(reference), [TOKEN_B, TOKEN_A])
        self.assertEqual(self.register(code, TOKEN_B, "push_unregister")[0], 200)
        self.assertEqual(self.tokens(reference), [TOKEN_A])

    def test_the_fourth_device_replaces_the_oldest(self):
        reference, code = self.new_request()
        for token in TOKENS:
            self.assertEqual(self.register(code, token)[0], 200)
        self.assertEqual(self.tokens(reference), [TOKEN_B, TOKEN_C, TOKEN_D])

    def test_bad_codes_and_bad_tokens_are_refused_and_store_nothing(self):
        reference, code = self.new_request()
        for wrong in ("short", "A" * 43, None, 5):
            status, body, _ = self.register(wrong, TOKEN_A)
            self.assertEqual((status, body["error"]), (404, "That private feedback link is invalid."))
        # A bad code and a bad token together: the code is checked first.
        self.assertEqual(self.register("A" * 43, "not-a-token")[0], 404)
        for bad in ("", "not-a-token", "ExponentPushToken[short]", "ExponentPushToken[" + "x" * 80 + "]",
                    TOKEN_A + ",extra", None, 7, ["x"]):
            self.assertEqual(self.register(code, bad)[0], 400, repr(bad))
        self.assertEqual(self.tokens(reference), [])

    def test_sixty_saved_requests_can_be_registered_without_a_rate_limit(self):
        reference, code = self.new_request()
        for number in range(60):
            token = f"ExponentPushToken[{number:022d}]"
            status, _, _ = self.register(code, token)
            self.assertEqual(status, 200, number)  # the general limit is 10; push has its own

    def test_old_actions_still_work_and_unknown_actions_are_refused(self):
        _, code = self.new_request()
        status, body, _ = self.call("POST", "/api/customer-feedback", {"action": "lookup", "token": code})
        self.assertEqual((status, body["status"]), (200, "pending"))
        self.assertEqual(self.call("POST", "/api/customer-feedback", {"action": "push_everything", "token": code})[0], 400)

    # -- sending --------------------------------------------------------------------------

    def test_a_status_change_sends_one_fixed_generic_message(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        self.sign_in()
        self.assertEqual(self.set_status(reference, "pending", "approved")[0], 200)
        self.assertTrue(push.wait_idle())
        self.assertEqual(len(self.fake.calls), 1)
        message = self.fake.calls[0][0]
        self.assertEqual((message["to"], message["title"], message["body"], message["data"]), (TOKEN_A, "AdenClean", FIXED_BODY, {"ref": reference}))
        sent = json.dumps(self.fake.calls)
        for private in ("Pat", "pat.private", "Two cats", "20910", code):
            self.assertNotIn(private, sent)
        self.assertEqual(self.tokens(reference), [TOKEN_A])  # kept: the request is not final

    def test_nothing_is_sent_when_push_is_off_or_nobody_registered(self):
        reference, code = self.new_request()
        self.sign_in()
        self.assertEqual(self.set_status(reference, "pending", "approved")[0], 200)  # no devices
        self.register(code, TOKEN_A)
        os.environ.pop("PUSH_ENABLED")
        self.assertEqual(self.set_status(reference, "approved", "pending")[0], 200)  # push off
        push.wait_idle()
        self.assertEqual(self.fake.calls, [])

    def test_reopening_notifies_and_a_final_status_clears_the_devices_after_one_send(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        self.register(code, TOKEN_B)
        self.sign_in()
        self.set_status(reference, "pending", "approved")
        self.set_status(reference, "approved", "pending")
        self.set_status(reference, "pending", "approved")
        self.set_status(reference, "approved", "completed")
        self.assertTrue(push.wait_idle())
        self.assertEqual(len(self.fake.calls), 4)
        self.assertEqual({m["to"] for m in self.fake.calls[-1]}, {TOKEN_A, TOKEN_B})
        self.assertEqual(self.tokens(reference), [])  # cleared after the notification about "completed"

    def test_a_dead_device_is_removed_and_the_others_are_kept(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        self.register(code, TOKEN_B)
        push.SENDER = self.fake = Fake(errors={TOKEN_A: "DeviceNotRegistered"})
        self.sign_in()
        self.set_status(reference, "pending", "approved")
        self.assertTrue(push.wait_idle())
        self.assertEqual(self.tokens(reference), [TOKEN_B])

    # -- the admin action never suffers ---------------------------------------------------

    def test_a_raising_sender_never_fails_the_admin_action_or_leaks_the_token(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)

        def boom(_messages):
            raise RuntimeError(f"secret detail with {TOKEN_A}")

        push.SENDER = boom
        self.sign_in()
        status, body, _ = self.set_status(reference, "pending", "approved")
        self.assertEqual((status, body["status"]), (200, "approved"))
        self.assertTrue(push.wait_idle())
        self.assertEqual(main.STORE.get_status("requests", reference), "approved")
        logged = self.logs.getvalue()
        self.assertIn("push delivery failed", logged)
        self.assertNotIn(TOKEN_A, logged)
        self.assertNotIn("secret detail", logged)

    def test_a_sender_that_hangs_does_not_slow_the_admin_response(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        release = threading.Event()
        self.addCleanup(release.set)
        push.SENDER = lambda _messages: release.wait(30) or [{"status": "ok"}]
        self.sign_in()
        started = time.monotonic()
        status, body, _ = self.set_status(reference, "pending", "approved")
        self.assertEqual((status, body["status"]), (200, "approved"))
        self.assertLess(time.monotonic() - started, 1.0)
        release.set()
        self.assertTrue(push.wait_idle())

    def test_the_real_sender_gives_up_on_a_server_that_never_answers(self):
        silent = socket.socket()
        silent.bind(("127.0.0.1", 0))
        silent.listen(5)
        self.addCleanup(silent.close)
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        push.SENDER = push.default_send
        with mock.patch.object(push, "EXPO_URL", f"http://127.0.0.1:{silent.getsockname()[1]}/send"), \
                mock.patch.object(push, "SEND_TIMEOUT_SECONDS", 0.5):
            self.sign_in()
            started = time.monotonic()
            self.assertEqual(self.set_status(reference, "pending", "approved")[0], 200)
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertTrue(push.wait_idle(10))
        self.assertIn("push delivery failed", self.logs.getvalue())

    def test_a_full_queue_drops_messages_without_raising_or_waiting(self):
        reference, code = self.new_request()
        self.register(code, TOKEN_A)
        release = threading.Event()
        self.addCleanup(release.set)
        push.SENDER = lambda _messages: release.wait(30) or [{"status": "ok"}]
        started = time.monotonic()
        for _ in range(push.QUEUE_SIZE + 50):
            push.notify_status_change(main.STORE, reference, "approved")
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn("push queue full", self.logs.getvalue())
        release.set()
        self.assertTrue(push.wait_idle(10))

    # -- the real HTTPS call --------------------------------------------------------------

    def test_the_real_sender_builds_the_expected_request(self):
        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"data": [{"status": "ok"}, {"status": "error", "details": {"error": "DeviceNotRegistered"}}]}).encode()

        with mock.patch("push.urllib.request.urlopen", return_value=Reply()) as urlopen:
            results = push.default_send([{"to": TOKEN_A}, {"to": TOKEN_B}], environ={})
        request = urlopen.call_args.args[0]
        self.assertEqual((request.full_url, request.get_method()), (push.EXPO_URL, "POST"))
        self.assertNotIn("Authorization", {k.title() for k in request.headers})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], push.SEND_TIMEOUT_SECONDS)
        self.assertEqual([r["error"] for r in results], [None, "DeviceNotRegistered"])
        with mock.patch("push.urllib.request.urlopen", return_value=Reply()) as urlopen:
            push.default_send([{"to": TOKEN_A}], environ={"EXPO_ACCESS_TOKEN": "t0ken"})
        self.assertEqual(urlopen.call_args.args[0].get_header("Authorization"), "Bearer t0ken")

    # -- privacy --------------------------------------------------------------------------

    def test_no_response_export_or_log_ever_contains_a_push_token(self):
        reference, code = self.new_request()
        for token in (TOKEN_A, TOKEN_B):
            self.register(code, token)
        self.sign_in()
        self.set_status(reference, "pending", "approved")
        push.wait_idle()
        seen = [
            self.call("POST", "/api/customer-feedback", {"action": "lookup", "token": code})[1],
            self.call("GET", "/api/admin/records?type=requests")[1],
            self.register(code, TOKEN_C)[1],
            self.register("A" * 43, TOKEN_D)[1],
            main.STORE.export_all(),
        ]
        text = json.dumps(seen) + self.logs.getvalue()
        for token in TOKENS:
            self.assertNotIn(token, text)
        self.assertNotIn("push_tokens", json.dumps(main.STORE.export_all()))

    def test_every_token_like_column_is_either_private_or_knowingly_exported(self):
        known = {"feedback_token_hash"}  # a hash that cannot be used as the private link; exported on purpose
        for table in storage.EXPORT_TABLES:
            for column in (c[0] for c in storage.APPWRITE_SCHEMA[table]["columns"]):
                if "token" in column or "push" in column:
                    private = column in storage.PRIVATE_COLUMNS.get(table, ())
                    self.assertTrue(private or column in known, f"{table}.{column} must be listed in PRIVATE_COLUMNS or known")


class TokenRuleTests(unittest.TestCase):
    def test_token_list_helpers(self):
        self.assertEqual(push.parse_tokens(None), [])
        self.assertEqual(push.parse_tokens(f"{TOKEN_A},garbage,{TOKEN_B}"), [TOKEN_A, TOKEN_B])
        self.assertIsNone(push.join_tokens([]))
        self.assertEqual(push.add_token([TOKEN_A, TOKEN_B, TOKEN_C], TOKEN_D), [TOKEN_B, TOKEN_C, TOKEN_D])
        self.assertLessEqual(len(push.join_tokens([TOKEN_A, TOKEN_B, TOKEN_C])), 255)  # fits the column
        self.assertLessEqual(len(push.join_tokens([f"ExponentPushToken[{'z' * 60}]"] * 3)), 255)

    def test_the_text_is_fixed_and_says_nothing_about_the_service(self):
        for word in ("clean", "deep", "approved", "declined", "name"):
            self.assertNotIn(word, push.BODY.lower())


if __name__ == "__main__":
    unittest.main()
