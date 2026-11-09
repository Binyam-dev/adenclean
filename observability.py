"""Structured logs and optional error monitoring.

Logs are one JSON object per line on stdout (Render collects stdout). They never include
request bodies, cookies, private link codes or customer details: only the method, the path
without its query string, the status, the duration, a request id and the visitor's address
(used to investigate abuse; the privacy policy says so).

Error monitoring is off unless SENTRY_DSN is set. When on, unhandled server errors go to
Sentry without request data or local variables.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

_SENTRY = None


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["error"] = record.exc_info[0].__name__
            entry["trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def release(environ=None):
    environ = os.environ if environ is None else environ
    return (environ.get("ADENCLEAN_RELEASE") or environ.get("RENDER_GIT_COMMIT") or "dev")[:40]


def configure(environ=None, stream=None):
    """Send every log record to stdout as JSON, and start Sentry if it is configured."""
    global _SENTRY
    environ = os.environ if environ is None else environ
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)

    dsn = environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger("adenclean").warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False
    sentry_sdk.init(
        dsn=dsn,
        release=release(environ),
        send_default_pii=False,
        include_local_variables=False,  # locals can hold names and emails
        max_request_body_size="never",
        traces_sample_rate=0,
    )
    _SENTRY = sentry_sdk
    return True


def capture(error, request_id=None, path=None):
    """Report an unexpected error. Never raises."""
    if _SENTRY is None:
        return
    try:
        with _SENTRY.new_scope() as scope:
            scope.set_tag("request_id", request_id or "")
            scope.set_tag("path", path or "")
            _SENTRY.capture_exception(error)
    except Exception:  # monitoring must never break a request
        logging.getLogger("adenclean").warning("could not report an error to monitoring")
