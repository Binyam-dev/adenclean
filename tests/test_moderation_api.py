"""Report, block, filter, suspend and the admin queue, end to end over HTTP on both stores."""

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import store as storage  # noqa: E402
from marketplace import bookings, mailer  # noqa: E402
from test_app import HAVE_APPWRITE, PASSWORD  # noqa: E402
from test_marketplace_api import NEXT_WEEK, TOMORROW  # noqa: E402
from test_payments import PaymentsCase  # noqa: E402

if HAVE_APPWRITE:
    from fake_appwrite import FakeTablesDB


class ModerationCase(PaymentsCase):
    def setUp(self):
        os.environ["VETTING_REQUIRED"] = "0"
        super().setUp()
        mailer.DEV_ALERTS.clear()

    # -- helpers -----------------------------------------------------------------

    def market(self):
        return main.STORE._marketplace

    def uid(self, email):
        return self.market().find_user_by_email(email)["id"]

    def admin_cookie(self):
        if not getattr(self, "_ops", None):
            self.add_admin("ops@example.com")
            self._ops = self.sign_in("ops@example.com")
        return self._ops

    def admin_get(self):
        return self.call("GET", "/api/admin/moderation", cookie=self.admin_cookie())

    def admin_act(self, report_id, action):
        return self.call("POST", f"/api/admin/moderation/{report_id}", {"action": action}, cookie=self.admin_cookie())

    def report(self, token, kind, target_id, reason="harassment", detail=None):
        payload = {"targetKind": kind, "targetId": target_id, "reason": reason}
        if detail:
            payload["detail"] = detail
        return self.v1("POST", "/api/v1/reports", payload, token)

    def open_job(self, customer, **overrides):
        return self.post_job(customer, **overrides)[1]["job"]["id"]

    def offer_on(self, cleaner, job_id, price=15_000, message=None):
        payload = {"priceCents": price}
        if message:
            payload["message"] = message
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", payload, cleaner)
        self.assertEqual(status, 201, body)
        return body["offer"]["id"]

    def two_parties(self):
        """A customer with an open job, and an activated cleaner with a ready payout account."""
        customer = self.sign_up("cust@example.com", "Sam")
        cleaner = self.ready_cleaner()
        return customer, cleaner, self.open_job(customer, notes="Two cats")

    # -- reporting -----------------------------------------------------------------

    def test_report_rules(self):
        customer, cleaner, job_id = self.two_parties()
        stranger = self.sign_up("stranger@example.com")
        self.assertEqual(self.report(customer, "job", job_id)[0], 400)  # your own content
        self.assertEqual(self.report(stranger, "job", job_id)[0], 404)  # cannot see it
        self.assertEqual(self.report(stranger, "job", "0" * 32)[0], 404)  # same answer as a missing one
        self.assertEqual(self.report(cleaner, "job", job_id, reason="nope")[0], 400)
        self.assertEqual(self.report(cleaner, "tweet", job_id)[0], 400)
        status, first = self.report(cleaner, "job", job_id, detail="Rude notes")
        self.assertEqual((status, first["merged"]), (201, False))
        status, again = self.report(cleaner, "job", job_id)
        self.assertEqual((status, again["merged"], again["reportId"]), (200, True, first["reportId"]))
        self.assertEqual(len(self.market().reports_by_reporter(self.uid("hana@example.com"))), 1)

    def test_report_limit_counts_new_reports_only_and_reopens_after_dismissal(self):
        customer = self.sign_up("cust@example.com")
        cleaner = self.ready_cleaner()
        job_ids = [self.open_job(customer) for _ in range(11)]
        ids = []
        for job_id in job_ids[:10]:
            status, body = self.report(cleaner, "job", job_id)
            self.assertEqual(status, 201, body)
            ids.append(body["reportId"])
        self.assertEqual(self.report(cleaner, "job", job_ids[0])[0], 200)  # merged: not counted, not refused
        status, body = self.report(cleaner, "job", job_ids[10])
        self.assertEqual(status, 429, body)
        # After a dismissal the same person may report the same job again.
        self.assertEqual(self.admin_act(ids[0], "dismiss")[0], 200)
        status, body = self.report(cleaner, "job", job_ids[0])
        self.assertEqual(status, 429)  # still over the hourly limit, which counts rows, not open ones
        for report in self.market().reports_by_reporter(self.uid("hana@example.com")):
            self.market().update_report(report["id"], {"created_at": "2000-01-01T00:00:00+00:00"})
        status, body = self.report(cleaner, "job", job_ids[0])
        self.assertEqual((status, body["merged"]), (201, False))

    def test_report_keeps_a_snapshot_after_the_content_is_gone(self):
        customer, cleaner, job_id = self.two_parties()
        status, body = self.report(cleaner, "job", job_id)
        self.assertEqual(status, 201)
        self.assertEqual(self.v1("POST", "/api/v1/auth/delete-account", {"confirm": "DELETE"}, customer)[0], 200)
        status, queue, _ = self.admin_get()
        item = queue["queue"][0]
        self.assertEqual((status, item["snapshot_text"], item["snapshot_name"], item["snapshot_status"]),
                         (200, "Two cats", "Sam", "open"))

    def test_reporter_identity_never_reaches_the_reported_person(self):
        customer, cleaner, job_id = self.two_parties()
        offer_id = self.offer_on(cleaner, job_id)
        reporter = self.uid("hana@example.com")
        self.assertEqual(self.report(cleaner, "job", job_id, detail="Rude")[0], 201)
        responses = [
            self.v1("GET", "/api/v1/me", token=customer),
            self.v1("GET", "/api/v1/jobs/mine", token=customer),
            self.v1("GET", f"/api/v1/jobs/{job_id}", token=customer),
            self.v1("GET", f"/api/v1/jobs/{job_id}/offers", token=customer),
            self.v1("GET", "/api/v1/blocks", token=customer),
            self.v1("POST", f"/api/v1/offers/{offer_id}/decline", {}, customer),
        ]
        for status, body in responses:
            self.assertNotIn(reporter, json.dumps(body))
            self.assertNotIn("Rude", json.dumps(body))
            self.assertNotIn("reporter", json.dumps(body).lower())

    def test_alert_goes_only_to_support_and_never_names_anyone(self):
        os.environ["MAIL_MODE"] = "dev"
        customer, cleaner, job_id = self.two_parties()
        self.report(cleaner, "job", job_id, reason="unsafe", detail="secret detail")
        self.assertEqual(len(mailer.DEV_ALERTS), 1)
        to, subject, body = mailer.DEV_ALERTS[0]
        self.assertEqual(to, "applications@adeneats.com")
        for private in (self.uid("hana@example.com"), self.uid("cust@example.com"), "hana@example.com",
                        "cust@example.com", "secret detail", "Two cats", "Sam", "Hana"):
            self.assertNotIn(private, subject + body)

    def test_a_failed_alert_never_fails_the_report(self):
        customer, cleaner, job_id = self.two_parties()  # sign-in needs mail, so turn it off afterwards
        os.environ["MAIL_MODE"] = "off"  # nothing is sent; the report is still saved
        self.assertEqual(self.report(cleaner, "job", job_id)[0], 201)
        self.assertEqual(mailer.DEV_ALERTS, [])

    # -- blocking ------------------------------------------------------------------

    def test_customer_block_hides_both_ways_withdraws_offers_and_is_idempotent(self):
        customer, cleaner, job_id = self.two_parties()
        offer_id = self.offer_on(cleaner, job_id)
        self.assertEqual([j["id"] for j in self.v1("GET", "/api/v1/jobs/open", token=cleaner)[1]["jobs"]], [job_id])
        status, first = self.v1("POST", f"/api/v1/offers/{offer_id}/block", {}, customer)
        self.assertEqual(status, 200, first)
        status, second = self.v1("POST", f"/api/v1/offers/{offer_id}/block", {}, customer)
        self.assertEqual((status, second["blockId"]), (200, first["blockId"]))  # idempotent
        market = self.market()
        self.assertEqual(market.get_offer(offer_id)["status"], "withdrawn")
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner)[1]["jobs"], [])
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}", token=cleaner)[0], 404)
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}/offers", token=cleaner)[0], 404)
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 9_000}, cleaner)
        self.assertEqual(status, 404, body)  # same answer as a job that does not exist
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}", token=customer)[0], 200)
        # Listing and unblocking: the name is shown, the user id is not.
        blocks = self.v1("GET", "/api/v1/blocks", token=customer)[1]["blocks"]
        self.assertEqual([b["name"] for b in blocks], ["Hana"])
        self.assertNotIn(self.uid("hana@example.com"), json.dumps(blocks))
        self.assertEqual(self.v1("POST", f"/api/v1/blocks/{blocks[0]['id']}/remove", {}, customer)[0], 200)
        self.assertEqual(self.v1("GET", "/api/v1/blocks", token=customer)[1]["blocks"], [])
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}", token=cleaner)[0], 200)
        self.assertEqual(market.get_offer(offer_id)["status"], "withdrawn")  # not restored

    def test_cleaner_can_block_a_customer_through_the_job(self):
        customer, cleaner, job_id = self.two_parties()
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/block", {}, customer)[0], 400)  # your own job
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/block", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner)[1]["jobs"], [])
        stranger = self.sign_up("stranger@example.com")
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/block", {}, stranger)[0], 404)

    def test_a_block_does_not_stop_a_live_booking(self):
        customer, cleaner, job_id = self.booked_job(price=15_000)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/block", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}", token=customer)[0], 200)
        self.pay(customer, job_id)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-out", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/confirm", {}, customer)[0], 200)
        self.assertEqual(self.market().get_job(job_id)["status"], "completed")

    def test_a_block_during_a_booking_still_hides_the_blockers_other_jobs(self):
        customer, cleaner, booked_id = self.booked_job(price=15_000)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{booked_id}/block", {}, cleaner)[0], 200)
        other_job = self.open_job(customer)  # a new job from the blocker's side of the pair
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner)[1]["jobs"], [])
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{other_job}/offers", {"priceCents": 9_000}, cleaner)[0], 404)
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{other_job}", token=cleaner)[0], 404)
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{booked_id}", token=cleaner)[0], 200)  # the booked job stays visible

    def test_accept_is_refused_after_a_block_or_suspension_made_since_the_offer(self):
        customer, cleaner, job_id = self.two_parties()
        offer_id = self.offer_on(cleaner, job_id)
        market = self.market()
        # A block row written directly, as if it landed between reading the offer and accepting it.
        market.create_block({"id": "b" * 32, "blocker_id": self.uid("cust@example.com"),
                             "blocked_id": self.uid("hana@example.com"), "active": 1, "created_at": "2026-11-09T00:00:00+00:00"})
        status, body = self.v1("POST", f"/api/v1/offers/{offer_id}/accept", {}, customer)
        self.assertEqual((status, body["error"]), (409, "This offer is no longer available."))
        self.assertEqual(market.get_job(job_id)["status"], "open")
        market.update_block("b" * 32, {"active": 0})
        market.update_user(self.uid("hana@example.com"), {"status": "suspended"})
        self.assertEqual(self.v1("POST", f"/api/v1/offers/{offer_id}/accept", {}, customer)[0], 409)
        self.assertEqual(market.get_job(job_id)["status"], "open")
        self.assertIsNone(market.booking_for_job(job_id))

    def test_racing_accept_and_block_never_leave_a_half_booking(self):
        customer, cleaner, _ = self.two_parties()
        for round_number in range(8):
            job_id = self.open_job(customer)
            offer_id = self.offer_on(cleaner, job_id)
            results = {}

            def accept():
                results["accept"] = self.v1("POST", f"/api/v1/offers/{offer_id}/accept", {}, customer)[0]

            def block():
                results["block"] = self.v1("POST", f"/api/v1/offers/{offer_id}/block", {}, customer)

            threads = [threading.Thread(target=accept), threading.Thread(target=block)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
            market = self.market()
            booked = market.get_job(job_id)["status"] == "booked"
            self.assertEqual(results["block"][0], 200)
            self.assertIn(results["accept"], (200, 409))
            self.assertEqual(booked, results["accept"] == 200, results)  # booked if and only if accept won
            self.assertEqual(market.booking_for_job(job_id) is not None, booked)
            if not booked:
                self.assertEqual(market.get_offer(offer_id)["status"], "withdrawn")
            # Lift the block so the next round starts clean.
            self.assertEqual(self.v1("POST", f"/api/v1/blocks/{results['block'][1]['blockId']}/remove", {}, customer)[0], 200)

    # -- filter --------------------------------------------------------------------

    def test_user_text_is_filtered_before_saving(self):
        customer, cleaner, job_id = self.two_parties()
        status, body = self.post_job(customer, notes="Call me on 240-342-6088")
        self.assertEqual(status, 400)
        self.assertIn("notes", body["error"])
        self.assertNotIn("240", body["error"])
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/offers",
                               {"priceCents": 10_000, "message": "mail me pat@example.com"}, cleaner)
        self.assertEqual(status, 400)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/offers",
                                 {"priceCents": 10_000, "message": "Happy to bring my own supplies."}, cleaner)[0], 201)
        self.assertEqual(self.post_job(customer, notes="Remove the soap scum and empty the trash.")[0], 201)

    def test_a_rejected_name_does_not_burn_the_sign_in_code(self):
        os.environ["MAIL_MODE"] = "dev"
        self.assertEqual(self.v1("POST", "/api/v1/auth/request-code", {"email": "new@example.com"})[0], 200)
        _, code = mailer.DEV_OUTBOX[-1]
        bad = {"email": "new@example.com", "code": code, "displayName": "Visit www.bad.com", "acceptTerms": True}
        self.assertEqual(self.v1("POST", "/api/v1/auth/verify-code", bad)[0], 400)
        good = dict(bad, displayName="Pat")
        status, body = self.v1("POST", "/api/v1/auth/verify-code", good)
        self.assertEqual(status, 200, body)  # the same code still works

    # -- admin ---------------------------------------------------------------------

    def test_admin_endpoints_work_with_the_admin_cookie_path(self):
        customer, cleaner, job_id = self.two_parties()
        self.report(cleaner, "job", job_id)
        status, _, headers = self.call("POST", "/api/admin/session", {"email": "ops@example.com", "password": PASSWORD})
        self.admin_cookie()
        status, _, headers = self.call("POST", "/api/admin/session", {"email": "ops@example.com", "password": PASSWORD})
        cookie_path = [p.split("=", 1)[1] for p in headers["Set-Cookie"].split("; ") if p.startswith("Path=")][0]
        urls = ["/api/admin/moderation", "/api/admin/moderation/" + "a" * 32]
        self.assertTrue(all(u.startswith(cookie_path) for u in urls), (cookie_path, urls))
        self.assertEqual(self.admin_get()[0], 200)
        self.assertEqual(self.call("GET", "/api/admin/moderation")[0], 401)  # no cookie, no queue
        self.assertEqual(self.call("POST", urls[1], {"action": "dismiss"})[0], 401)

    def test_admin_actions_and_a_resolved_report_cannot_be_actioned_twice(self):
        customer, cleaner, job_id = self.two_parties()
        offer_id = self.offer_on(cleaner, job_id, message="Happy to help")
        job_report = self.report(cleaner, "job", job_id)[1]["reportId"]
        offer_report = self.report(customer, "offer", offer_id)[1]["reportId"]
        status, queue, _ = self.admin_get()
        self.assertEqual([q["id"] for q in queue["queue"]], [job_report, offer_report])  # oldest first
        self.assertEqual(self.admin_act(job_report, "explode")[0], 400)
        self.assertEqual(self.admin_act(job_report, "remove_content")[0], 200)
        self.assertIsNone(self.market().get_job(job_id)["notes"])
        self.assertEqual(self.admin_act(job_report, "dismiss")[0], 409)  # already handled
        self.assertEqual(self.admin_act(offer_report, "remove_content")[0], 200)
        self.assertIsNone(self.market().get_offer(offer_id)["message"])
        report = self.market().get_report(job_report)
        self.assertEqual((report["status"], report["action"], report["resolved_by"]), ("actioned", "remove_content", "ops@example.com"))
        self.assertEqual(self.admin_get()[1]["queue"], [])

    def test_suspend_closes_open_items_blocks_writes_and_is_reversible(self):
        customer, cleaner, job_id = self.two_parties()
        offer_id = self.offer_on(cleaner, job_id)
        report_id = self.report(customer, "offer", offer_id)[1]["reportId"]
        status, body, _ = self.admin_act(report_id, "suspend_user")
        self.assertEqual((status, body["warning"]), (200, None))
        market = self.market()
        self.assertEqual(market.get_user(self.uid("hana@example.com"))["status"], "suspended")
        self.assertEqual(market.get_offer(offer_id)["status"], "withdrawn")
        # A suspended person cannot post, offer or browse, but can still read who they are and delete the account.
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner)[0], 403)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 9_000}, cleaner)[0], 403)
        status, me = self.v1("GET", "/api/v1/me", token=cleaner)
        self.assertEqual((status, me["user"]["suspended"]), (200, True))
        # No new session either.
        os.environ["MAIL_MODE"] = "dev"
        self.v1("POST", "/api/v1/auth/request-code", {"email": "hana@example.com"})
        _, code = mailer.DEV_OUTBOX[-1]
        status, body = self.v1("POST", "/api/v1/auth/verify-code", {"email": "hana@example.com", "code": code})
        self.assertEqual(status, 403)
        # Suspending an account that is already suspended is refused; unsuspend restores access.
        second = self.report(customer, "offer", offer_id, reason="spam")  # the first report is closed, so this is new
        self.assertEqual(second[0], 201)
        self.assertEqual(self.admin_act(second[1]["reportId"], "suspend_user")[0], 409)  # already suspended
        self.assertEqual(self.market().get_report(second[1]["reportId"])["status"], "open")  # a refused action resolves nothing
        third = self.report(customer, "offer", offer_id, reason="other")
        self.assertEqual(third[1]["reportId"], second[1]["reportId"])  # merged into the still-open one
        self.assertEqual(self.admin_act(second[1]["reportId"], "unsuspend_user")[0], 200)
        self.assertEqual(self.admin_act(second[1]["reportId"], "unsuspend_user")[0], 409)  # now handled
        self.assertEqual(self.v1("GET", "/api/v1/jobs/open", token=cleaner)[0], 200)

    def test_suspending_during_a_live_booking_warns_and_keeps_the_booking_working(self):
        customer, cleaner, job_id = self.booked_job(price=15_000)
        offer_id = self.market().get_job(job_id)["booked_offer_id"]
        report_id = self.report(customer, "offer", offer_id, reason="unsafe")[1]["reportId"]
        status, body, _ = self.admin_act(report_id, "suspend_user")
        self.assertEqual(status, 200)
        self.assertIn("live booking", body["warning"])
        # The suspended cleaner can still finish the job they are on; the customer can pay and confirm.
        self.pay(customer, job_id)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-out", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/confirm", {}, customer)[0], 200)

    def test_admin_cancel_and_refund_returns_the_full_price_once(self):
        customer, cleaner, job_id = self.booked_job(price=15_000)
        self.pay(customer, job_id)
        offer_id = self.market().get_job(job_id)["booked_offer_id"]
        report_id = self.report(customer, "offer", offer_id, reason="unsafe")[1]["reportId"]
        status, body, _ = self.admin_act(report_id, "cancel_booking_refund")
        self.assertEqual(status, 200, body)
        self.assertEqual(self.market().get_job(job_id)["status"], "cancelled")
        self.assertEqual(self.stripe.count("refund"), 1)
        self.assertEqual([c for c in self.stripe.calls if c[0] == "refund"][0][2], 15_000)  # full price, no late fee
        self.assertEqual(self.stripe.count("transfer"), 0)
        self.assertEqual(bookings.reconcile(self.ledger(job_id))["platform_balance"], 0)
        again = self.report(customer, "offer", offer_id, reason="fake")  # a second action: nothing left to cancel
        self.assertEqual(self.admin_act(again[1]["reportId"], "cancel_booking_refund")[0], 409)
        self.assertEqual(self.stripe.count("refund"), 1)  # still only one refund

    def test_deleting_an_account_clears_report_text_and_blocks(self):
        customer, cleaner, job_id = self.two_parties()
        report_id = self.report(cleaner, "job", job_id, detail="Details I wrote")[1]["reportId"]
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/block", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", "/api/v1/auth/delete-account", {"confirm": "DELETE"}, cleaner)[0], 200)
        market = self.market()
        self.assertIsNone(market.get_report(report_id)["detail"])
        self.assertEqual(market.blocks_by(self.uid_deleted()), [])

    def uid_deleted(self):
        return next(u["id"] for u in self.market().t.find("users", {"status": "deleted"}))


class SqliteModerationTests(ModerationCase, unittest.TestCase):
    def make_store(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        return storage.SqliteStore(Path(self.directory.name) / "m.sqlite3")


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwriteModerationTests(ModerationCase, unittest.TestCase):
    def make_store(self):
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean", tables_db=FakeTablesDB())


def load_tests(loader, tests, pattern):
    own = [n for n in ModerationCase.__dict__ if n.startswith("test_")]
    suite = unittest.TestSuite()
    for cls in (SqliteModerationTests, AppwriteModerationTests):
        suite.addTests(cls(name) for name in own)
    return suite


if __name__ == "__main__":
    unittest.main()
