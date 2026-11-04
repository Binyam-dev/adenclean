"""End-to-end marketplace API tests over real HTTP, against both storage backends."""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store as storage  # noqa: E402
from marketplace import mailer  # noqa: E402
from test_app import AppCase, HAVE_APPWRITE  # noqa: E402

if HAVE_APPWRITE:
    from fake_appwrite import FakeTablesDB

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()


class MarketplaceCase(AppCase):
    def setUp(self):
        for key, value in {"MARKETPLACE_ENABLED": "1", "MAIL_MODE": "dev"}.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k) if o is None else os.environ.__setitem__(k, o))
        mailer.DEV_OUTBOX.clear()
        super().setUp()

    def v1(self, method, path, payload=None, token=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def sign_up(self, email, name="Pat"):
        self.assertEqual(self.v1("POST", "/api/v1/auth/request-code", {"email": email})[0], 200)
        sent_to, code = mailer.DEV_OUTBOX[-1]
        self.assertEqual(sent_to, email)
        status, body = self.v1("POST", "/api/v1/auth/verify-code",
                               {"email": email, "code": code, "displayName": name, "acceptTerms": True})
        self.assertEqual(status, 200, body)
        return body["token"]

    def make_cleaner(self, email, name="Hana"):
        token = self.sign_up(email, name)
        if not getattr(self, "_admin_cookie", None):
            self.add_admin()
            self._admin_cookie = self.sign_in()
        status, body, _ = self.call("POST", "/api/v1/admin/cleaners", {"email": email, "active": True},
                                    cookie=self._admin_cookie)
        self.assertEqual(status, 200, body)
        return token

    def post_job(self, token, **overrides):
        payload = {"serviceType": "deep", "zip": "20910", "bedrooms": 2, "bathrooms": 1,
                   "supplies": "cleaner", "dateFrom": TOMORROW, "dateTo": NEXT_WEEK, "notes": "Two cats"}
        payload.update(overrides)
        return self.v1("POST", "/api/v1/jobs", payload, token)

    # -- tests -----------------------------------------------------------------

    def test_sign_in_rules(self):
        self.v1("POST", "/api/v1/auth/request-code", {"email": "a@example.com"})
        _, code = mailer.DEV_OUTBOX[-1]
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.v1("POST", "/api/v1/auth/verify-code",
                                 {"email": "a@example.com", "code": wrong, "acceptTerms": True})[0], 400)
        status, body = self.v1("POST", "/api/v1/auth/verify-code", {"email": "a@example.com", "code": code})
        self.assertEqual(status, 400)  # new account must accept terms
        self.assertIn("terms", body["error"])
        self.v1("POST", "/api/v1/auth/request-code", {"email": "a@example.com"})
        _, code = mailer.DEV_OUTBOX[-1]
        ok = self.v1("POST", "/api/v1/auth/verify-code", {"email": "a@example.com", "code": code, "acceptTerms": True})
        self.assertEqual(ok[0], 200)
        reused = self.v1("POST", "/api/v1/auth/verify-code", {"email": "a@example.com", "code": code})
        self.assertEqual(reused[0], 400)  # single use
        me = self.v1("GET", "/api/v1/me", token=ok[1]["token"])
        self.assertEqual((me[0], me[1]["user"]["roles"]), (200, ["customer"]))
        self.assertEqual(self.v1("GET", "/api/v1/me", token="1.2.3.4")[0], 401)

    def test_post_offer_counter_accept_books_exactly_once(self):
        customer = self.sign_up("cust@example.com", "Sam")
        cleaner_a = self.make_cleaner("hana@example.com", "Hana")
        cleaner_b = self.make_cleaner("mimi@example.com", "Mimi")
        status, job = self.post_job(customer)
        self.assertEqual(status, 201, job)
        job_id = job["job"]["id"]

        feed = self.v1("GET", "/api/v1/jobs/open", token=cleaner_a)[1]["jobs"]
        self.assertEqual([j["id"] for j in feed], [job_id])
        self.assertNotIn("customer_id", feed[0])

        status, a = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 15_000}, cleaner_a)
        self.assertEqual(status, 201, a)
        status, b = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 14_000}, cleaner_b)
        self.assertEqual(status, 201, b)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 13_000}, cleaner_b)[0], 409)

        offers_seen = self.v1("GET", f"/api/v1/jobs/{job_id}/offers", token=customer)[1]["offers"]
        self.assertEqual({o["cleaner_name"] for o in offers_seen}, {"Hana", "Mimi"})
        self.assertEqual(len(self.v1("GET", f"/api/v1/jobs/{job_id}/offers", token=cleaner_a)[1]["offers"]), 1)

        a_id = a["offer"]["id"]
        self.assertEqual(self.v1("POST", f"/api/v1/offers/{a_id}/counter", {"priceCents": 13_000}, customer)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/offers/{a_id}/counter", {"priceCents": 12_000}, customer)[0], 409)
        status, booked = self.v1("POST", f"/api/v1/offers/{a_id}/accept", {}, cleaner_a)
        self.assertEqual(status, 200, booked)
        self.assertEqual((booked["job"]["status"], booked["priceCents"]), ("booked", 13_000))

        b_id = b["offer"]["id"]
        self.assertEqual(self.v1("POST", f"/api/v1/offers/{b_id}/accept", {}, customer)[0], 409)
        statuses = {o["id"]: o["status"] for o in self.v1("GET", f"/api/v1/jobs/{job_id}/offers", token=customer)[1]["offers"]}
        self.assertEqual(statuses, {a_id: "accepted", b_id: "expired"})
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner_b)[1]["jobs"], [])

    def test_customers_cannot_see_the_job_feed_or_offer_on_their_own_job(self):
        customer = self.sign_up("cust@example.com")
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=customer)[0], 403)
        both = self.make_cleaner("both@example.com")
        job_id = self.post_job(both)[1]["job"]["id"]
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=both)[1]["jobs"], [])
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 10_000}, both)
        self.assertEqual(status, 409)
        self.assertIn("own job", body["error"])

    def test_job_rules(self):
        customer = self.sign_up("cust@example.com")
        self.assertEqual(self.post_job(customer, zip="90210")[0], 400)
        self.assertEqual(self.post_job(customer, serviceType="mold-removal")[0], 400)
        self.assertEqual(self.post_job(customer, dateFrom="2020-01-01")[0], 400)
        self.assertEqual(self.post_job(customer, bathrooms=0)[0], 400)
        self.assertEqual(self.post_job(customer)[0], 201)

    def test_delete_account_cancels_open_jobs_and_ends_the_session(self):
        customer = self.sign_up("gone@example.com")
        job_id = self.post_job(customer)[1]["job"]["id"]
        self.assertEqual(self.v1("POST", "/api/v1/auth/delete-account", {"confirm": "nope"}, customer)[0], 400)
        status, body = self.v1("POST", "/api/v1/auth/delete-account", {"confirm": "DELETE"}, customer)
        self.assertEqual((status, body["cancelledJobs"]), (200, 1))
        self.assertEqual(self.v1("GET", "/api/v1/me", token=customer)[0], 401)
        cleaner = self.make_cleaner("hana@example.com")
        self.assertNotIn(job_id, [j["id"] for j in self.v1("GET", "/api/v1/jobs/open", token=cleaner)[1]["jobs"]])
        # The same email can sign up again as a new person.
        self.assertTrue(self.sign_up("gone@example.com"))

    def test_marketplace_is_off_unless_enabled(self):
        os.environ["MARKETPLACE_ENABLED"] = "0"
        self.assertEqual(self.v1("GET", "/api/v1/me")[0], 404)

    def test_mail_off_means_no_codes(self):
        os.environ["MAIL_MODE"] = "off"
        status, body = self.v1("POST", "/api/v1/auth/request-code", {"email": "x@example.com"})
        self.assertEqual(status, 503)
        self.assertEqual(mailer.DEV_OUTBOX, [])


class SqliteMarketplaceTests(MarketplaceCase, unittest.TestCase):
    def make_store(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        return storage.SqliteStore(Path(self.directory.name) / "m.sqlite3")


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwriteMarketplaceTests(MarketplaceCase, unittest.TestCase):
    def make_store(self):
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean",
                                     tables_db=FakeTablesDB())


if __name__ == "__main__":
    unittest.main()
