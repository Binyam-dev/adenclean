"""End-user sign-in by emailed one-time code, and signed session tokens.

No end-user passwords are stored. Codes are 6 digits, single use, valid 10 minutes, and
allow 5 wrong guesses. Only an HMAC of the code is stored.
"""

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
MAX_CODES_PER_HOUR = 5
SESSION_SECONDS = 30 * 24 * 60 * 60  # mobile sessions last 30 days
TERMS_VERSION = "2026-11-09"  # adds the content-conduct clause (new sign-ups record this version)
PRIVACY_VERSION = "2026-11-04"


class AuthError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _now():
    return datetime.now(timezone.utc)


def _key(secret, purpose):
    return hmac.new(secret.encode(), purpose.encode(), hashlib.sha256).digest()


def code_hash(secret, email, code):
    return hmac.new(_key(secret, "login-code"), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_code(store, secret, email, now=None):
    """Create a code and return it for the mailer. Raises AuthError(429) when overused."""
    now = now or _now()
    recent = [c for c in store.recent_login_codes(email)
              if datetime.fromisoformat(c["created_at"]) > now - timedelta(hours=1)]
    if len(recent) >= MAX_CODES_PER_HOUR:
        raise AuthError(429, "Too many codes requested. Try again in an hour.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    store.add_login_code({
        "id": uuid.uuid4().hex, "email": email, "code_hash": code_hash(secret, email, code),
        "created_at": now.isoformat(), "expires_at": (now + CODE_TTL).isoformat(),
        "attempts": 0, "used": 0,
    })
    return code


def check_code(store, secret, email, code, now=None):
    """Consume the newest unused code if it matches. Generic errors either way."""
    now = now or _now()
    wrong = AuthError(400, "That code is wrong or has expired. Request a new one.")
    if not (isinstance(code, str) and len(code) == 6 and code.isdigit()):
        raise wrong
    live = [c for c in store.recent_login_codes(email) if not c["used"]
            and datetime.fromisoformat(c["expires_at"]) > now and c["attempts"] < MAX_ATTEMPTS]
    if not live:
        raise wrong
    latest = live[0]
    if not hmac.compare_digest(latest["code_hash"], code_hash(secret, email, code)):
        store.update_login_code(latest["id"], {"attempts": latest["attempts"] + 1})
        raise wrong
    store.update_login_code(latest["id"], {"used": 1})
    return True


def make_token(secret, user_id, now=None):
    expires = int((now or time.time()) + SESSION_SECONDS)
    payload = f"{expires}.{user_id}.{secrets.token_hex(8)}"
    sig = hmac.new(_key(secret, "user-session"), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_token(secret, token, now=None):
    """Return the user id from a valid token, or None."""
    if not isinstance(token, str) or token.count(".") != 3:
        return None
    expires, user_id, nonce, sig = token.split(".")
    payload = f"{expires}.{user_id}.{nonce}"
    good = hmac.new(_key(secret, "user-session"), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return None
    return user_id


def sign_in(store, email, display_name, accepted_terms, ip, now=None):
    """Find or create the user after a verified code. New users must accept the terms."""
    now = now or _now()
    user = store.find_user_by_email(email)
    if user and user["status"] == "suspended":
        raise AuthError(403, "This account is suspended. Contact AdenClean for help.")
    if user and user["status"] == "active":
        return user, False
    if accepted_terms is not True:
        raise AuthError(400, "Accept the terms and privacy policy to create an account.")
    user = {
        "id": uuid.uuid4().hex, "email": email, "display_name": display_name,
        "roles": "customer", "status": "active", "home_zip": None, "language_codes": None,
        "created_at": now.isoformat(), "deleted_at": None,
    }
    store.create_user(user)
    for kind, version in (("terms", TERMS_VERSION), ("privacy", PRIVACY_VERSION)):
        store.add_consent({"id": uuid.uuid4().hex, "user_id": user["id"], "kind": kind,
                           "version": version, "ip": ip, "created_at": now.isoformat()})
    return user, True


def roles_of(user):
    return set(filter(None, (user.get("roles") or "").split(",")))


def delete_account(store, user, now=None):
    """Anonymize the account. Payment, tax and safety records are kept separately by law."""
    now = now or _now()
    store.update_user(user["id"], {
        "email": f"deleted-{user['id']}@deleted.invalid", "display_name": "Deleted user",
        "status": "deleted", "home_zip": None, "language_codes": None, "roles": "",
        "deleted_at": now.isoformat(),
    })
    cancelled = close_open_items(store, user["id"], now)
    store.deactivate_blocks_for(user["id"])  # their blocks end with the account
    store.clear_report_details(user["id"])  # free text they wrote in their own reports
    return cancelled


def close_open_items(store, user_id, now):
    """Cancel a person's open jobs (as customer) and withdraw their open offers (as cleaner).

    Bookings are never touched here: money and safety flows finish on their own.
    Idempotent. The caller holds BOOKING_LOCK. Returns how many jobs were cancelled.
    """
    cancelled = 0
    for job in store.jobs_for_customer(user_id):
        if job["status"] in ("draft", "open", "expired"):
            store.update_job(job["id"], {"status": "cancelled", "notes": None,
                                         "status_updated_at": now.isoformat()})
            cancelled += 1
    for offer in store.offers_by_cleaner(user_id):
        if offer["status"] in ("pending", "countered"):
            store.update_offer(offer["id"], {"status": "withdrawn", "message": None,
                                             "updated_at": now.isoformat()})
    return cancelled


def suspend(store, user, now=None):
    """Suspend an active account and close its open jobs and offers. Caller holds BOOKING_LOCK."""
    if user["status"] != "active":
        raise AuthError(409, "Only an active account can be suspended.")
    store.update_user(user["id"], {"status": "suspended"})
    return close_open_items(store, user["id"], now or _now())


def unsuspend(store, user):
    if user["status"] != "suspended":
        raise AuthError(409, "This account is not suspended.")
    store.update_user(user["id"], {"status": "active"})
