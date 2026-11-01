"""Password hashing for AdenClean admin accounts (standard library only)."""

import base64
import hashlib
import hmac
import os

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 64 * 1024 * 1024
_DUMMY = None


def _derive(password, salt, n, r, p):
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32
    )


def hash_password(password):
    salt = os.urandom(16)
    digest = _derive(password, salt, _N, _R, _P)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(actual, expected)


def burn_time(password):
    """Spend the same effort as a real check so unknown emails are not detectable by timing."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(base64.b64encode(os.urandom(18)).decode("ascii"))
    verify_password(password, _DUMMY)


def password_problem(password):
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Use at most {PASSWORD_MAX_LENGTH} characters."
    return ""
