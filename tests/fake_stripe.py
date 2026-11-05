"""In-memory Stripe for tests. Mirrors the gateway's method signatures and Stripe's rule
that a repeated Idempotency-Key returns the original object instead of acting twice."""

import itertools
import json
import time

from marketplace.stripe_gateway import sign_for_tests

WEBHOOK_SECRET = "whsec_test_fake"


class FakeStripe:
    def __init__(self):
        self.calls = []
        self.by_key = {}
        self.accounts = {}
        self._ids = itertools.count(1)

    def _new(self, prefix):
        return f"{prefix}_{next(self._ids):04d}"

    def _once(self, key, make):
        if key and key in self.by_key:
            return self.by_key[key]
        obj = make()
        if key:
            self.by_key[key] = obj
        return obj

    def create_account(self, email, idempotency_key):
        self.calls.append(("create_account", email))
        def make():
            acct = {"id": self._new("acct"), "email": email, "payouts_enabled": False}
            self.accounts[acct["id"]] = acct
            return acct
        return self._once(idempotency_key, make)

    def account_link(self, account_id, refresh_url, return_url):
        self.calls.append(("account_link", account_id))
        return {"url": f"https://connect.stripe.test/setup/{account_id}"}

    def retrieve_account(self, account_id):
        return dict(self.accounts[account_id])

    def create_payment_intent(self, amount_cents, transfer_group, metadata, idempotency_key):
        self.calls.append(("payment_intent", amount_cents, transfer_group, dict(metadata)))
        def make():
            pid = self._new("pi")
            return {"id": pid, "client_secret": f"{pid}_secret", "amount": amount_cents, "metadata": dict(metadata)}
        return self._once(idempotency_key, make)

    def create_transfer(self, amount_cents, destination, transfer_group, source_transaction, idempotency_key):
        self.calls.append(("transfer", amount_cents, destination, source_transaction))
        return self._once(idempotency_key, lambda: {"id": self._new("tr"), "amount": amount_cents})

    def create_refund(self, payment_intent_id, amount_cents, idempotency_key):
        self.calls.append(("refund", payment_intent_id, amount_cents))
        return self._once(idempotency_key, lambda: {"id": self._new("re"), "amount": amount_cents})

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)

    # webhook helpers
    def event(self, event_type, obj, event_id=None):
        return {"id": event_id or self._new("evt"), "type": event_type, "data": {"object": obj}}

    def succeeded(self, intent):
        obj = dict(intent, amount_received=intent["amount"], latest_charge=self._new("ch"))
        return self.event("payment_intent.succeeded", obj)

    @staticmethod
    def signed(event, timestamp=None, secret=WEBHOOK_SECRET):
        payload = json.dumps(event).encode()
        return payload, sign_for_tests(payload, secret, int(timestamp or time.time()))
