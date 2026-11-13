"""Push notifications about a customer request's status (Expo push service).

Design rules (docs/SPEC-push-notifications.md):
- Off unless PUSH_ENABLED=1.
- A notification is best effort. It is queued after the status change is saved and sent by one
  background thread, once, with a short timeout. It never delays or fails an admin action.
- The text is fixed and generic. No name, email, address or free text is ever sent.
- Push tokens are private: never returned by an API, never written to a log or a backup.
- Up to MAX_TOKENS devices per request. A token is removed when the person turns notifications
  off, when Expo says it is dead, and after the first notification about a final status.
"""

import json
import logging
import os
import queue
import re
import ssl
import threading
import time
import urllib.request

from validation import ApiError

log = logging.getLogger("adenclean.push")

ACTIONS = {"push_register", "push_unregister"}
TOKEN_PATTERN = re.compile(r"Expo(?:nent)?PushToken\[[A-Za-z0-9_-]{10,60}\]")
MAX_TOKENS = 3
EXPO_URL = "https://exp.host/--/api/v2/push/send"
SEND_TIMEOUT_SECONDS = 5
QUEUE_SIZE = 100
TITLE = "AdenClean"
BODY = "Update on your request. Tap for details."
CHANNEL = "request-updates"
NOTIFY_STATUSES = {"approved", "declined", "completed", "cancelled", "pending"}
FINAL_STATUSES = {"completed", "cancelled"}


def enabled(environ=None):
    return (os.environ if environ is None else environ).get("PUSH_ENABLED") == "1"


# -- tokens in one column: "tokenA,tokenB" -------------------------------------------------

def parse_tokens(value):
    return [t for t in (value or "").split(",") if TOKEN_PATTERN.fullmatch(t)]


def join_tokens(tokens):
    return ",".join(tokens) or None


def add_token(tokens, token):
    """Newest last. Adding a fourth device drops the oldest."""
    return [t for t in tokens if t != token][-(MAX_TOKENS - 1):] + [token]


def clean_token(value):
    if not isinstance(value, str) or not TOKEN_PATTERN.fullmatch(value):
        raise ApiError(400, "Notifications could not be turned on for this device.")
    return value


# -- storage (Appwrite row column; the store's lock keeps read-change-write consistent) -----

def get_tokens(store, request_id):
    row = store._call(store.db.get_row, table_id="customer_requests", row_id=request_id)
    return parse_tokens(row.data.get("push_tokens"))


def set_tokens(store, request_id, tokens):
    store._call(store.db.update_row, table_id="customer_requests", row_id=request_id,
                data={"push_tokens": join_tokens(tokens)})


def change_tokens(store, request_id, change):
    with store._lock:
        tokens = change(get_tokens(store, request_id))
        set_tokens(store, request_id, tokens)
    return tokens


def handle_action(store, request, action, payload):
    """push_register / push_unregister for the request whose private code was just checked."""
    token = clean_token(payload.get("pushToken"))
    if action == "push_register":
        change_tokens(store, request["id"], lambda tokens: add_token(tokens, token))
    else:
        change_tokens(store, request["id"], lambda tokens: [t for t in tokens if t != token])
    return 200, {"ok": True}


# -- sending ----------------------------------------------------------------------------------

def default_send(messages, environ=None):
    """One HTTPS call to Expo. Returns [{"status": "ok"|"error", "error": str|None}] per message.
    Raises on any transport problem; the worker logs only the exception type."""
    environ = os.environ if environ is None else environ
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if environ.get("EXPO_ACCESS_TOKEN"):
        headers["Authorization"] = "Bearer " + environ["EXPO_ACCESS_TOKEN"]
    bundle = environ.get("PUSH_CA_BUNDLE")
    context = ssl.create_default_context(cafile=bundle) if bundle else None  # never disable checking
    request = urllib.request.Request(EXPO_URL, data=json.dumps(messages).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS, context=context) as response:
        results = json.loads(response.read())["data"]
    return [{"status": r.get("status"), "error": (r.get("details") or {}).get("error")} for r in results]


SENDER = default_send  # tests replace this

_QUEUE = queue.Queue(maxsize=QUEUE_SIZE)
_WORKER = None
_WORKER_LOCK = threading.Lock()


def notify_status_change(store, request_id, new_status):
    """Call after a status change has been saved. Never raises and never waits."""
    if not enabled() or new_status not in NOTIFY_STATUSES:
        return
    try:
        _QUEUE.put_nowait((store, request_id, new_status))
    except queue.Full:
        log.warning("push queue full; message dropped")
        return
    _ensure_worker()


def _ensure_worker():
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_run, name="push-sender", daemon=True)
            _WORKER.start()


def _run():
    while True:
        store, request_id, status = _QUEUE.get()
        try:
            _deliver(store, request_id, status)
        except Exception as error:  # noqa: BLE001 - best effort; log the type only
            log.warning("push delivery failed", extra={"fields": {"error": type(error).__name__}})
        finally:
            _QUEUE.task_done()


def _deliver(store, request_id, status):
    tokens = get_tokens(store, request_id)
    if not tokens:
        return
    messages = [{"to": t, "title": TITLE, "body": BODY, "sound": "default", "channelId": CHANNEL,
                 "data": {"ref": request_id}} for t in tokens]
    results = SENDER(messages)
    dead = {t for t, r in zip(tokens, results) if r.get("error") == "DeviceNotRegistered"}
    if status in FINAL_STATUSES:
        change_tokens(store, request_id, lambda _current: [])
    elif dead:
        change_tokens(store, request_id, lambda current: [t for t in current if t not in dead])


def wait_idle(timeout=5.0):
    """For tests: True once everything queued has been handled."""
    deadline = time.monotonic() + timeout
    with _QUEUE.all_tasks_done:
        while _QUEUE.unfinished_tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _QUEUE.all_tasks_done.wait(remaining)
    return True
