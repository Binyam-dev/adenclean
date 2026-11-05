"""Checkr client (stdlib only): candidates, hosted invitations, webhook signatures.

Uses Checkr's staging API unless CHECKR_LIVE_OK=1, so development never orders a real
background check. The invitation is hosted by Checkr: the cleaner enters their SSN and
other details there, so those never touch AdenClean's servers.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("adenclean.checkr")
STAGING = "https://api.checkr-staging.com/v1"
LIVE = "https://api.checkr.com/v1"


class CheckrError(RuntimeError):
    pass


class CheckrGateway:
    def __init__(self, api_key, package, environ=None):
        environ = os.environ if environ is None else environ
        if not api_key or not package:
            raise CheckrError("Background checks are not set up yet.")
        self._key, self.package = api_key, package
        self.base = LIVE if environ.get("CHECKR_LIVE_OK") == "1" else STAGING

    def _post(self, path, data):
        auth = base64.b64encode(f"{self._key}:".encode()).decode()
        request = urllib.request.Request(
            self.base + path, data=urllib.parse.urlencode(data).encode(), method="POST",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            log.error("Checkr POST %s failed: %s", path, error.code)
            raise CheckrError("The background-check provider refused the request.") from error
        except OSError as error:
            log.error("Checkr POST %s unreachable (%s)", path, type(error).__name__)
            raise CheckrError("The background-check provider could not be reached.") from error

    def create_candidate(self, email, user_id):
        return self._post("/candidates", {"email": email, "custom_id": user_id})

    def create_invitation(self, candidate_id, state="MD"):
        return self._post("/invitations", {
            "candidate_id": candidate_id, "package": self.package,
            "work_locations[][country]": "US", "work_locations[][state]": state,
        })


def verify_signature(payload, header, key):
    """X-Checkr-Signature is an HMAC-SHA256 hex digest of the raw body (per Checkr's docs)."""
    if not key or not header:
        return False
    expected = hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.strip())


def sign_for_tests(payload, key):
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()
