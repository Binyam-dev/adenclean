"""Thin Stripe client (stdlib only) for Connect Express with separate charges and transfers.

Test mode only unless STRIPE_LIVE_OK=1 is set, so a live key cannot charge real cards by
accident. Every money-moving call carries an Idempotency-Key, so a retry never charges,
refunds or pays out twice. Keys are never logged.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("adenclean.stripe")
API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE = 300  # seconds, Stripe's documented default


class StripeError(RuntimeError):
    def __init__(self, message, status=0, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def _flatten(data, prefix=""):
    """Stripe's form encoding: {"a": {"b": 1}} -> [("a[b]", "1")]."""
    items = []
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else key
        if isinstance(value, dict):
            items.extend(_flatten(value, name))
        elif isinstance(value, bool):
            items.append((name, "true" if value else "false"))
        elif value is not None:
            items.append((name, str(value)))
    return items


class StripeGateway:
    def __init__(self, secret_key, environ=None):
        environ = os.environ if environ is None else environ
        if not secret_key:
            raise StripeError("Payments are not set up yet.")
        if not secret_key.startswith("sk_test_") and environ.get("STRIPE_LIVE_OK") != "1":
            raise StripeError("Refusing a live Stripe key without STRIPE_LIVE_OK=1.")
        self._key = secret_key

    def _request(self, method, path, data=None, idempotency_key=None):
        body = urllib.parse.urlencode(_flatten(data or {})).encode() if method == "POST" else None
        headers = {"Authorization": f"Bearer {self._key}"}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(API + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read()).get("error", {})
            except ValueError:
                detail = {}
            log.error("Stripe %s %s failed: %s %s", method, path, error.code, detail.get("code"))
            raise StripeError(detail.get("message") or "The payment provider refused the request.",
                              error.code, detail.get("code")) from error
        except OSError as error:
            log.error("Stripe %s %s unreachable (%s)", method, path, type(error).__name__)
            raise StripeError("The payment provider could not be reached.") from error

    # Connect Express accounts for cleaners
    def create_account(self, email, idempotency_key):
        return self._request("POST", "/accounts", {
            "type": "express", "country": "US", "email": email,
            "capabilities": {"transfers": {"requested": True}},
            "business_type": "individual",
        }, idempotency_key)

    def account_link(self, account_id, refresh_url, return_url):
        return self._request("POST", "/account_links", {
            "account": account_id, "refresh_url": refresh_url, "return_url": return_url,
            "type": "account_onboarding",
        })

    def retrieve_account(self, account_id):
        return self._request("GET", f"/accounts/{urllib.parse.quote(account_id)}")

    # Charging the customer, paying the cleaner, refunds
    def create_payment_intent(self, amount_cents, transfer_group, metadata, idempotency_key):
        return self._request("POST", "/payment_intents", {
            "amount": amount_cents, "currency": "usd", "transfer_group": transfer_group,
            "automatic_payment_methods": {"enabled": True}, "metadata": metadata,
        }, idempotency_key)

    def create_transfer(self, amount_cents, destination, transfer_group, source_transaction, idempotency_key):
        return self._request("POST", "/transfers", {
            "amount": amount_cents, "currency": "usd", "destination": destination,
            "transfer_group": transfer_group, "source_transaction": source_transaction,
        }, idempotency_key)

    def create_refund(self, payment_intent_id, amount_cents, idempotency_key):
        return self._request("POST", "/refunds", {
            "payment_intent": payment_intent_id, "amount": amount_cents,
        }, idempotency_key)


def verify_webhook(payload, header, secret, now=None, tolerance=SIGNATURE_TOLERANCE):
    """Return the parsed event if the Stripe-Signature header is valid, else raise StripeError."""
    if not secret:
        raise StripeError("Webhook secret is not configured.", 400)
    timestamp, signatures = None, []
    for part in (header or "").split(","):
        prefix, _, value = part.strip().partition("=")
        if prefix == "t":
            timestamp = value
        elif prefix == "v1":
            signatures.append(value)
    if not timestamp or not timestamp.isdigit() or not signatures:
        raise StripeError("Malformed signature header.", 400)
    signed = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise StripeError("Signature does not match.", 400)
    if abs((now or time.time()) - int(timestamp)) > tolerance:
        raise StripeError("Signature timestamp is outside the tolerance.", 400)
    return json.loads(payload)


def sign_for_tests(payload, secret, timestamp):
    """Build a Stripe-Signature header the way Stripe does (used only by tests)."""
    signed = str(timestamp).encode() + b"." + payload
    return f"t={timestamp},v1={hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()}"
