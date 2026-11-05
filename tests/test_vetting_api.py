"""Vetting end to end over HTTP: apply, disclosure and signed authorization, hosted identity
and background checks, signed vendor webhooks, admin approval and the full adverse-action path."""

import itertools
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_v1_payments  # noqa: E402
import api_v1_vetting  # noqa: E402
import main  # noqa: E402
import store as storage  # noqa: E402
from fake_stripe import FakeStripe  # noqa: E402
from marketplace.checkr_gateway import sign_for_tests  # noqa: E402
from test_app import HAVE_APPWRITE  # noqa: E402
from test_marketplace_api import MarketplaceCase  # noqa: E402

if HAVE_APPWRITE:
    from fake_appwrite import FakeTablesDB

CHECKR_KEY = "checkr_test_key"
NOTE = "Burglary conviction in 2023, three years ago; this work means unsupervised access to homes."


class FakeCheckr:
    def __init__(self):
        self.ids = itertools.count(1)
        self.calls = []

    def create_candidate(self, email, user_id):
        self.calls.append(("candidate", email))
        return {"id": f"cand_{next(self.ids)}"}

    def create_invitation(self, candidate_id, state="MD"):
        self.calls.append(("invitation", candidate_id, state))
        return {"id": f"inv_{next(self.ids)}", "invitation_url": f"https://apply.checkr.test/{candidate_id}"}


class VettingCase(MarketplaceCase):
    def setUp(self):
        env = {"PAYMENTS_ENABLED": "1", "STRIPE_WEBHOOK_SECRET": "whsec_test_fake", "CHECKR_WEBHOOK_KEY": CHECKR_KEY}
        for key, value in env.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k) if o is None else os.environ.__setitem__(k, o))
        self.stripe, self.checkr = FakeStripe(), FakeCheckr()
        api_v1_payments.GATEWAY_FACTORY = lambda: self.stripe
        api_v1_vetting.CHECKR_FACTORY = lambda: self.checkr
        self.addCleanup(setattr, api_v1_payments, "GATEWAY_FACTORY", None)
        self.addCleanup(setattr, api_v1_vetting, "CHECKR_FACTORY", None)
        super().setUp()
        os.environ["VETTING_REQUIRED"] = "1"  # the real rule, not the Phase 1 shortcut

    def post_raw(self, path, payload, headers):
        request = urllib.request.Request(self.base + path, data=payload, method="POST",
                                         headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def checkr_event(self, candidate, result, event_id="evt_c1", key=CHECKR_KEY):
        body = json.dumps({"id": event_id, "type": "report.completed", "data": {"object": {
            "id": "rpt_1", "object": "report", "status": "complete", "result": result, "candidate_id": candidate}}}).encode()
        return self.post_raw("/api/v1/webhooks/checkr", body, {"X-Checkr-Signature": sign_for_tests(body, key)})

    def identity_event(self, user_id, verified=True):
        kind = "identity.verification_session.verified" if verified else "identity.verification_session.requires_input"
        payload, header = FakeStripe.signed(self.stripe.event(kind, {"id": "vs_x", "metadata": {"user_id": user_id}}),
                                            secret="whsec_test_fake")
        return self.post_raw("/api/v1/webhooks/stripe", payload, {"Stripe-Signature": header})

    def applicant(self, email="hana@example.com"):
        token = self.sign_up(email, "Hana")
        me = self.v1("GET", "/api/v1/me", token=token)[1]["user"]
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/apply", {"over18": True}, token)[0], 201)
        return token, me["id"]

    def checked(self, result):
        token, uid = self.applicant()
        self.v1("POST", "/api/v1/cleaner/authorize", {"authorize": True, "fullName": "Hana Tesfaye"}, token)
        self.v1("POST", "/api/v1/cleaner/identity", {}, token)
        self.assertEqual(self.identity_event(uid), 200)
        self.v1("POST", "/api/v1/cleaner/background", {}, token)
        candidate = main.STORE._marketplace.get_vetting(uid)["candidate_ref"]
        self.assertEqual(self.checkr_event(candidate, result), 200)
        return token, uid

    def admin(self):
        if not getattr(self, "_ops", None):
            self.add_admin("ops@example.com")
            self._ops = self.sign_in("ops@example.com")
        return self._ops

    def decide(self, uid, **payload):
        status, body, _ = self.call("POST", f"/api/v1/admin/vetting/{uid}", payload, cookie=self.admin())
        return status, body

    # -- tests -----------------------------------------------------------------

    def test_clear_path_ends_with_an_activated_cleaner(self):
        token, uid = self.applicant()
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/background", {}, token)[0], 409)  # no signed authorization
        disclosure = self.v1("GET", "/api/v1/cleaner/disclosure", token=token)[1]
        self.assertIn("consumer report", disclosure["text"])
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/authorize", {"authorize": True, "fullName": "Hana Tesfaye"}, token)[0], 200)
        status, ident = self.v1("POST", "/api/v1/cleaner/identity", {}, token)
        self.assertTrue(ident["url"].startswith("https://verify.stripe.test/"))
        self.assertEqual(self.identity_event(uid), 200)
        status, bg = self.v1("POST", "/api/v1/cleaner/background", {}, token)
        self.assertEqual(status, 200, bg)
        self.assertTrue(bg["url"].startswith("https://apply.checkr.test/"))
        self.assertEqual(self.checkr.calls[-1][2], "MD")
        candidate = main.STORE._marketplace.get_vetting(uid)["candidate_ref"]
        self.assertEqual(self.checkr_event(candidate, "clear"), 200)
        self.assertEqual(self.v1("GET", "/api/v1/cleaner/status", token=token)[1]["vetting"]["status"], "in_review")

        queue = self.call("GET", "/api/v1/admin/vetting", cookie=self.admin())[1]["queue"]
        self.assertEqual([q["user_id"] for q in queue], [uid])
        self.assertEqual(self.decide(uid, action="approve")[0], 200)
        self.assertIn("cleaner", self.v1("GET", "/api/v1/me", token=token)[1]["user"]["roles"])
        kinds = {c["kind"] for c in main.STORE._marketplace.t.find("consents", {"user_id": uid})}
        self.assertEqual(kinds, {"terms", "privacy", "background_check"})

    def test_consider_path_follows_both_adverse_action_steps(self):
        token, uid = self.checked("consider")
        self.assertEqual(self.decide(uid, action="approve", note="ok")[0], 409)  # needs an assessment
        self.assertEqual(self.decide(uid, action="pre_adverse", reason="theft_burglary", note=NOTE)[0], 400)  # notice not sent
        status, body = self.decide(uid, action="pre_adverse", reason="arrest_only", note=NOTE, noticeSentViaCheckr=True)
        self.assertEqual(status, 409)
        self.assertIn("Arrests", body["error"])
        self.assertEqual(self.decide(uid, action="pre_adverse", reason="theft_burglary", note=NOTE, noticeSentViaCheckr=True)[0], 200)
        self.assertEqual(self.decide(uid, action="final_adverse", noticeSentViaCheckr=True)[0], 409)  # waiting period

        self.assertEqual(self.v1("POST", "/api/v1/cleaner/dispute", {}, token)[0], 200)
        market = main.STORE._marketplace
        record = market.get_vetting(uid)
        market.save_vetting(dict(record, dispute_deadline=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()))
        self.assertEqual(self.decide(uid, action="final_adverse", noticeSentViaCheckr=True)[0], 409)  # dispute open
        self.assertEqual(self.decide(uid, action="resolve_dispute")[0], 200)
        status, body = self.decide(uid, action="final_adverse", noticeSentViaCheckr=True)
        self.assertEqual((status, body["vetting"]["status"]), (200, "denied"))
        self.assertNotIn("cleaner", self.v1("GET", "/api/v1/me", token=token)[1]["user"]["roles"])

    def test_vetting_cannot_be_skipped_by_manual_activation(self):
        self.sign_up("skip@example.com")
        status, body, _ = self.call("POST", "/api/v1/admin/cleaners", {"email": "skip@example.com", "active": True},
                                    cookie=self.admin())
        self.assertEqual(status, 409)
        self.assertIn("vetting", body["error"])

    def test_vendor_webhooks_are_authenticated_and_replay_safe(self):
        token, uid = self.applicant()
        self.v1("POST", "/api/v1/cleaner/authorize", {"authorize": True, "fullName": "Hana Tesfaye"}, token)
        self.v1("POST", "/api/v1/cleaner/background", {}, token)
        candidate = main.STORE._marketplace.get_vetting(uid)["candidate_ref"]
        self.assertEqual(self.checkr_event(candidate, "clear", key="wrong"), 400)
        self.assertEqual(main.STORE._marketplace.get_vetting(uid)["background_status"], "invited")
        self.assertEqual(self.checkr_event(candidate, "clear"), 200)
        self.assertEqual(self.checkr_event(candidate, "consider"), 200)  # same event id replayed
        self.assertEqual(main.STORE._marketplace.get_vetting(uid)["background_status"], "clear")

    def test_failed_identity_is_a_plain_decline(self):
        token, uid = self.applicant()
        self.v1("POST", "/api/v1/cleaner/authorize", {"authorize": True, "fullName": "Hana Tesfaye"}, token)
        self.v1("POST", "/api/v1/cleaner/identity", {}, token)
        self.assertEqual(self.identity_event(uid, verified=False), 200)
        self.assertEqual(self.decide(uid, action="approve")[0], 409)
        self.assertEqual(self.decide(uid, action="decline_identity", note="Selfie did not match the ID")[1]["vetting"]["status"], "denied")

    def test_applicants_must_be_adults_and_apply_once(self):
        token = self.sign_up("teen@example.com")
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/apply", {}, token)[0], 400)
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/apply", {"over18": True}, token)[0], 201)
        self.assertEqual(self.v1("POST", "/api/v1/cleaner/apply", {"over18": True}, token)[0], 409)


class SqliteVettingTests(VettingCase, unittest.TestCase):
    def make_store(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        return storage.SqliteStore(Path(self.directory.name) / "v.sqlite3")


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwriteVettingTests(VettingCase, unittest.TestCase):
    def make_store(self):
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean", tables_db=FakeTablesDB())


def load_tests(loader, tests, pattern):
    own = [n for n in VettingCase.__dict__ if n.startswith("test_")]
    suite = unittest.TestSuite()
    for cls in (SqliteVettingTests, AppwriteVettingTests):
        suite.addTests(cls(name) for name in own)
    return suite


if __name__ == "__main__":
    unittest.main()
