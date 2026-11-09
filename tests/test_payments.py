"""Payments end to end over HTTP with a fake Stripe: charge, hold, release, tips, refunds,
webhook signatures and replays, and ledger reconciliation. Runs on both storage backends."""

import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_v1_payments  # noqa: E402
import main  # noqa: E402
import store as storage  # noqa: E402
from fake_stripe import WEBHOOK_SECRET, FakeStripe  # noqa: E402
from marketplace import bookings  # noqa: E402
from marketplace.stripe_gateway import StripeError, StripeGateway  # noqa: E402
from test_app import HAVE_APPWRITE  # noqa: E402
from test_marketplace_api import MarketplaceCase  # noqa: E402

if HAVE_APPWRITE:
    from fake_appwrite import FakeTablesDB


class PaymentsCase(MarketplaceCase):
    def setUp(self):
        for key, value in {"PAYMENTS_ENABLED": "1", "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET}.items():
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k) if o is None else os.environ.__setitem__(k, o))
        self.stripe = FakeStripe()
        api_v1_payments.GATEWAY_FACTORY = lambda: self.stripe
        self.addCleanup(setattr, api_v1_payments, "GATEWAY_FACTORY", None)
        super().setUp()

    def webhook(self, event, timestamp=None, secret=WEBHOOK_SECRET):
        payload, header = FakeStripe.signed(event, timestamp, secret)
        request = urllib.request.Request(self.base + "/api/v1/webhooks/stripe", data=payload, method="POST",
                                         headers={"Content-Type": "application/json", "Stripe-Signature": header})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def ready_cleaner(self, email="hana@example.com"):
        token = self.make_cleaner(email, "Hana")
        status, body = self.v1("POST", "/api/v1/payouts/onboard", {}, token)
        self.assertEqual(status, 200, body)
        acct = next(iter(a for a in self.stripe.accounts.values() if a["email"] == email))
        acct["payouts_enabled"] = True
        self.assertEqual(self.webhook(self.stripe.event("account.updated", dict(acct))), 200)
        return token

    def booked_job(self, price=15_000, **job):
        customer = self.sign_up("cust@example.com", "Sam")
        cleaner = self.ready_cleaner()
        job_id = self.post_job(customer, **job)[1]["job"]["id"]
        offer = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": price}, cleaner)[1]["offer"]
        self.assertEqual(self.v1("POST", f"/api/v1/offers/{offer['id']}/accept", {}, customer)[0], 200)
        return customer, cleaner, job_id

    def pay(self, customer, job_id):
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/pay", {}, customer)
        self.assertEqual(status, 200, body)
        intent = self.stripe.by_key[[k for k in self.stripe.by_key if k.startswith("pi:booking:")][-1]]
        self.assertEqual(self.webhook(self.stripe.succeeded(intent)), 200)
        return intent

    def ledger(self, job_id):
        market = main.STORE._marketplace
        return market.ledger_for(market.booking_for_job(job_id)["id"])

    # -- tests -----------------------------------------------------------------

    def test_full_money_flow_reconciles(self):
        customer, cleaner, job_id = self.booked_job(price=15_000)
        booking = self.v1("GET", f"/api/v1/jobs/{job_id}/booking", token=cleaner)[1]["booking"]
        self.assertEqual((booking["payment_status"], booking["fee_cents"], booking["payout_cents"]), ("unpaid", 2_250, 12_750))
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, cleaner)[0], 409)  # not paid yet

        self.pay(customer, job_id)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/pay", {}, customer)[0], 409)  # no double charge
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, cleaner)[0], 200)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-out", {}, cleaner)[0], 200)

        status, tip = self.v1("POST", f"/api/v1/jobs/{job_id}/tip", {"tipCents": 2_000}, customer)
        self.assertEqual(status, 200, tip)
        tip_intent = self.stripe.by_key[[k for k in self.stripe.by_key if k.startswith("pi:tip:")][0]]
        self.assertEqual(self.webhook(self.stripe.succeeded(tip_intent)), 200)
        self.assertEqual(self.stripe.count("transfer"), 0)  # nothing paid out before confirmation

        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/confirm", {}, customer)[0], 200)
        transfers = sorted(c[1] for c in self.stripe.calls if c[0] == "transfer")
        self.assertEqual(transfers, [2_000, 12_750])  # tip 100% to the cleaner, price minus 15%
        totals = bookings.reconcile(self.ledger(job_id))
        self.assertEqual(totals, {"in": 17_000, "refunds": 0, "transfers": 14_750, "platform_balance": 2_250})
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}", token=customer)[1]["job"]["status"], "completed")

    def test_webhook_signatures_and_replays(self):
        customer, _, job_id = self.booked_job()
        self.v1("POST", f"/api/v1/jobs/{job_id}/pay", {}, customer)
        intent = self.stripe.by_key[[k for k in self.stripe.by_key if k.startswith("pi:booking:")][0]]
        event = self.stripe.succeeded(intent)
        self.assertEqual(self.webhook(event, secret="whsec_wrong"), 400)
        self.assertEqual(self.webhook(event, timestamp=time.time() - 600), 400)  # outside 5-minute tolerance
        self.assertEqual(self.webhook(event), 200)
        self.assertEqual(self.webhook(event), 200)  # replay
        same_charge_new_event = dict(event, id="evt_other")
        self.assertEqual(self.webhook(same_charge_new_event), 200)
        self.assertEqual([e["entry_type"] for e in self.ledger(job_id)], ["charge"])  # recorded once

    def test_late_customer_cancellation_pays_the_cleaner_and_refunds_the_rest(self):
        # The server starts a job at noon UTC on its date. Use the next noon, which is always under 24 hours away.
        now = datetime.now(timezone.utc)
        tomorrow = (now.date() if now.hour < 12 else now.date() + timedelta(days=1)).isoformat()
        customer, _, job_id = self.booked_job(price=10_000, dateFrom=tomorrow, dateTo=tomorrow)
        self.pay(customer, job_id)
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/cancel", {}, customer)
        self.assertEqual(status, 200, body)
        self.assertEqual((body["refundCents"], body["cleanerFeeCents"]), (7_500, 2_500))
        self.assertEqual(bookings.reconcile(self.ledger(job_id))["platform_balance"], 0)

    def test_early_cancellation_is_a_full_refund_and_cleaner_cancel_has_no_penalty(self):
        customer, cleaner, job_id = self.booked_job(price=10_000)  # starts in 7 days
        self.pay(customer, job_id)
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/cancel-booking", {}, cleaner)
        self.assertEqual((status, body["refundCents"], body["cleanerFeeCents"]), (200, 10_000, 0))
        self.assertEqual(self.stripe.count("transfer"), 0)

    def test_auto_release_waits_48_hours(self):
        customer, cleaner, job_id = self.booked_job()
        self.pay(customer, job_id)
        self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, cleaner)
        self.v1("POST", f"/api/v1/jobs/{job_id}/check-out", {}, cleaner)
        self.add_admin("ops@example.com")
        cookie = self.sign_in("ops@example.com")
        self.assertEqual(self.call("POST", "/api/v1/admin/release-due", {}, cookie=cookie)[1]["released"], 0)
        market = main.STORE._marketplace
        booking = market.booking_for_job(job_id)
        market.update_booking(booking["id"], {"checked_out_at": (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()})
        self.assertEqual(self.call("POST", "/api/v1/admin/release-due", {}, cookie=cookie)[1]["released"], 1)
        self.assertEqual(self.stripe.count("transfer"), 1)

    def test_fee_rate_is_frozen_at_booking(self):
        customer, cleaner, job_id = self.booked_job(price=10_000)
        os.environ["PLATFORM_FEE_BPS"] = "3000"
        self.addCleanup(os.environ.pop, "PLATFORM_FEE_BPS", None)
        payout = self.v1("GET", f"/api/v1/jobs/{job_id}/booking", token=cleaner)[1]["booking"]["payout_cents"]
        self.assertEqual(payout, 8_500)

    def test_cleaners_must_finish_payout_setup_before_quoting(self):
        customer = self.sign_up("cust@example.com")
        cleaner = self.make_cleaner("new@example.com")
        job_id = self.post_job(customer)[1]["job"]["id"]
        status, body = self.v1("POST", f"/api/v1/jobs/{job_id}/offers", {"priceCents": 10_000}, cleaner)
        self.assertEqual(status, 403)
        self.assertIn("payouts", body["error"])

    def test_only_the_right_person_moves_the_booking(self):
        customer, cleaner, job_id = self.booked_job()
        stranger = self.sign_up("x@example.com")
        self.assertEqual(self.v1("GET", f"/api/v1/jobs/{job_id}/booking", token=stranger)[0], 404)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/pay", {}, cleaner)[0], 403)
        self.pay(customer, job_id)
        self.assertEqual(self.v1("POST", f"/api/v1/jobs/{job_id}/check-in", {}, customer)[0], 409)


class GatewaySafetyTests(unittest.TestCase):
    def test_live_keys_are_refused_without_explicit_opt_in(self):
        with self.assertRaises(StripeError):
            StripeGateway("sk_live_abc", environ={})
        StripeGateway("sk_live_abc", environ={"STRIPE_LIVE_OK": "1"})
        StripeGateway("sk_test_abc", environ={})

    def test_missing_key_is_a_clear_error(self):
        with self.assertRaises(StripeError):
            StripeGateway("", environ={})


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwritePaymentTests(PaymentsCase, unittest.TestCase):
    def make_store(self):
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean", tables_db=FakeTablesDB())


def load_tests(loader, tests, pattern):
    """Run only the tests defined in this file, not the inherited app and marketplace ones."""
    own = [n for n in PaymentsCase.__dict__ if n.startswith("test_")]
    suite = unittest.TestSuite()
    for cls in (AppwritePaymentTests,):
        suite.addTests(cls(name) for name in own)
    suite.addTests(loader.loadTestsFromTestCase(GatewaySafetyTests))
    return suite


if __name__ == "__main__":
    unittest.main()
