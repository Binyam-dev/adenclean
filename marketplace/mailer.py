"""Sends sign-in codes. Off by default so no real person is emailed until the owner opts in.

MAIL_MODE=off     (default) sign-in is unavailable; the API says so plainly
MAIL_MODE=dev     codes are kept in memory for tests and local runs, never sent anywhere
MAIL_MODE=resend  sends through Resend with RESEND_API_KEY and MAIL_FROM
"""

import json
import logging
import os
import urllib.request

log = logging.getLogger("adenclean.mailer")
DEV_OUTBOX = []  # (email, code) pairs, dev mode only


class MailError(RuntimeError):
    pass


def mode(environ=None):
    return (environ or os.environ).get("MAIL_MODE", "off").strip().lower()


def send_code(email, code, environ=None):
    environ = environ or os.environ
    current = mode(environ)
    if current == "dev":
        DEV_OUTBOX.append((email, code))
        return
    if current == "resend":
        key, sender = environ.get("RESEND_API_KEY"), environ.get("MAIL_FROM")
        if not key or not sender:
            raise MailError("Email sign-in is not configured.")
        body = json.dumps({
            "from": sender, "to": [email], "subject": f"Your AdenClean code: {code}",
            "text": f"Your AdenClean sign-in code is {code}. It expires in 10 minutes.\n"
                    "If you did not ask for it, ignore this email.",
        }).encode()
        request = urllib.request.Request(
            "https://api.resend.com/emails", data=body, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 300:
                    raise MailError("The email could not be sent.")
        except OSError as error:
            log.error("Resend request failed (%s)", type(error).__name__)  # never log the key
            raise MailError("The email could not be sent.") from error
        return
    raise MailError("Email sign-in is not turned on yet.")
