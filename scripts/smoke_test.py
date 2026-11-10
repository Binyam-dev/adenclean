"""Walk the customer flows (and the admin flow, if you give it a login) against a running server.

    python scripts/smoke_test.py https://adenclean.onrender.com
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=... python scripts/smoke_test.py https://adenclean.onrender.com

Customer flows: send a request, check it by its private code, try a review before the service
is complete (must be refused), and check bad input and a bad code are refused.
With an admin login it also assigns, approves and completes the request, then leaves a review
and an issue report and moderates both.

It writes ONE test request named "SMOKE TEST - ignore" with an example.com address. No email is
sent to anyone. Without an admin login that record stays "pending" in the admin list; cancel it
there. Prints PASS or FAIL per step, never a secret or a private code. Exit code 1 on failure.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

TEST_NAME = "SMOKE TEST - ignore"


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookie = None

    def call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.status, _json(response.read()), response.headers
        except urllib.error.HTTPError as error:
            return error.code, _json(error.read()), error.headers


def _json(raw):
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


def run(base, admin_email=None, admin_password=None, out=print):
    """Returns True if every step passed. Steps that need a newer server than the one running are skipped."""
    client = Client(base)
    results = []

    def step(name, ok, detail=""):
        results.append(ok)
        out(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
        return ok

    status, body, _ = client.call("GET", "/healthz")
    step("health check answers", status == 200 and body.get("ok") is True, f"HTTP {status}")
    status, body, _ = client.call("GET", "/health?deep=1")
    if status == 404:
        out("SKIP  deep health check (this server is older than the /health endpoint)")
    else:
        step("deep health check reads storage", status == 200 and body.get("database") == "ok", f"HTTP {status}")

    when = (date.today() + timedelta(days=30)).isoformat()
    request = {"fullName": TEST_NAME, "email": "smoke-test@example.com", "area": "20910", "serviceType": "deep",
               "preferredDate": when, "preferredTime": "morning", "notes": "Automated smoke test.", "consent": True}
    status, body, _ = client.call("POST", "/api/service-requests", request)
    saved = step("flow 1: a request is saved", status == 201 and body.get("reference") and body.get("feedbackToken"), f"HTTP {status}")
    if not saved:
        return False
    reference, token = body["reference"], body["feedbackToken"]

    status, body, _ = client.call("POST", "/api/service-requests", dict(request, fullName=""))
    step("bad input is refused", status == 400, f"HTTP {status}")
    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "lookup", "token": "x" * 43})
    step("a wrong private code is refused", status == 404, f"HTTP {status}")

    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "lookup", "token": token})
    step("flow 2: the request is found by its private code", status == 200 and body.get("status") == "pending" and body.get("ready") is False, f"HTTP {status}, status {body.get('status')}")
    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "review", "token": token, "rating": 5, "message": "Smoke test review.", "consent": True})
    step("a review before the service is complete is refused", status == 409, f"HTTP {status}")

    if not (admin_email and admin_password):
        out(f"NOTE  no admin login given: request {reference} stays pending. Cancel it in the admin page.")
        return all(results)

    status, body, headers = client.call("POST", "/api/admin/session", {"email": admin_email, "password": admin_password})
    cookie = (headers.get("Set-Cookie") or "").split(";")[0]
    if not step("admin: sign in", status == 200 and bool(cookie), f"HTTP {status}"):
        return False
    client.cookie = cookie

    def admin_status(record_type, record_id, expected, new):
        return client.call("POST", "/api/admin/records", {"type": record_type, "id": record_id, "expectedStatus": expected,
                                                          "status": new, "note": "smoke test"})[0]

    status, listing, _ = client.call("GET", "/api/admin/records?type=requests")
    found = [r for r in listing.get("records", []) if r["id"] == reference]
    step("admin: the request is in the list", status == 200 and len(found) == 1, f"HTTP {status}")
    status, body, _ = client.call("POST", "/api/admin/assignment", {"id": reference, "assignedTo": "Smoke test"})
    step("admin: assign the request", status == 200 and body.get("assignedTo") == "Smoke test", f"HTTP {status}")
    step("admin: approve", admin_status("requests", reference, "pending", "approved") == 200)
    step("admin: mark complete", admin_status("requests", reference, "approved", "completed") == 200)

    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "lookup", "token": token})
    step("the customer now sees it as complete", status == 200 and body.get("ready") is True)
    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "review", "token": token, "rating": 5, "message": "Smoke test review.", "consent": True})
    step("flow 3: a review is saved", status == 201, f"HTTP {status}")
    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "review", "token": token, "rating": 4, "message": "A second review.", "consent": True})
    step("a second review is refused", status == 409, f"HTTP {status}")
    status, body, _ = client.call("POST", "/api/customer-feedback", {"action": "issue", "token": token, "message": "Smoke test issue report.", "consent": True})
    step("flow 3: an issue report is saved", status == 201, f"HTTP {status}")

    for record_type, first, new in (("reviews", "new", "reviewed"), ("issues", "open", "resolved")):
        status, listing, _ = client.call("GET", f"/api/admin/records?type={record_type}")
        mine = [r for r in listing.get("records", []) if r.get("full_name") == TEST_NAME and r.get("status") == first]
        if not step(f"admin: the {record_type[:-1]} is listed", status == 200 and bool(mine), f"HTTP {status}"):
            continue
        step(f"admin: moderate the {record_type[:-1]}", admin_status(record_type, mine[0]["id"], first, new) == 200)
    status, _, headers = client.call("POST", "/api/admin/logout")
    cleared = "max-age=0" in (headers.get("Set-Cookie") or "").lower()
    if cleared:
        client.cookie = None  # do what a browser does with the clearing cookie
    step("admin: sign out clears the session cookie", status == 200 and cleared, f"HTTP {status}")
    status = client.call("GET", "/api/admin/records?type=requests")[0]
    step("admin: signed out, the admin list is refused", status == 401, f"HTTP {status}")
    return all(results)


def main(argv):
    if len(argv) != 1 or not argv[0].startswith(("http://", "https://")):
        print(__doc__)
        return 2
    ok = run(argv[0], os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD"))
    print("\nALL STEPS PASSED" if ok else "\nSOME STEPS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
