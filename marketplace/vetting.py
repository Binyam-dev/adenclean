"""Cleaner vetting: identity check, FCRA-compliant background check, admin review.

FCRA sequence enforced here (not legal advice; counsel must review the policy):
1. A standalone disclosure and the cleaner's written (typed-name) authorization, recorded
   with the disclosure version and time, BEFORE any report is ordered.
2. The report is ordered from a consumer reporting agency (Checkr). Its contents stay with
   the vendor; we store only references, status and decisions.
3. A "consider" result needs an individualized assessment with a job-related reason.
   Arrests that did not lead to a conviction are never a reason.
4. Pre-adverse action: notice with a copy of the report and the Summary of Rights (sent by
   the vendor), then a waiting period of N business days during which the cleaner can dispute.
5. Only after the wait, with no open dispute: the final adverse action notice.
Identity failures are not consumer reports, so they are a plain decline with a reason.
"""

from datetime import datetime, timedelta

DISCLOSURE_VERSION = "2026-11-04"
ADVERSE_WAIT_BUSINESS_DAYS = 5  # "reasonable" period; 5 business days is common practice
MIN_NOTE = 20

# Written, job-related criteria. The owner and counsel set the lookback periods.
REASONS = {
    "violent_offense": "Conviction for a violent offense",
    "sexual_offense": "Conviction for a sexual offense or sex-offender registry match",
    "theft_burglary": "Conviction for theft, burglary or robbery",
    "fraud": "Conviction for fraud or identity theft",
    "other_job_related": "Other conviction directly related to working inside people's homes",
}
FORBIDDEN_REASONS = {"arrest_only": "Arrests that did not lead to a conviction cannot be used."}


class VettingError(ValueError):
    pass


def new_record(user_id, now):
    return {
        "id": user_id, "status": "applied", "consent_at": None, "consent_name": None,
        "disclosure_version": None, "identity_status": "not_started", "identity_ref": None,
        "background_status": "not_started", "candidate_ref": None, "report_ref": None,
        "pre_adverse_at": None, "dispute_deadline": None, "dispute_open": 0, "final_adverse_at": None,
        "decision_reason": None, "assessment_note": None, "decided_by": None,
        "created_at": now.isoformat(), "updated_at": now.isoformat(),
    }


def add_business_days(start, days):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday-Friday; federal holidays are not skipped (conservative: counsel may add them)
            added += 1
    return current


def _open(record):
    if record["status"] in ("approved", "denied", "withdrawn"):
        raise VettingError(f"This application is already {record['status']}.")


def record_consent(record, typed_name, authorized, now):
    _open(record)
    if authorized is not True:
        raise VettingError("Authorize the background check to continue.")
    name = (typed_name or "").strip()
    if len(name) < 3:
        raise VettingError("Type your full legal name to sign.")
    return dict(record, consent_at=now.isoformat(), consent_name=name[:120],
                disclosure_version=DISCLOSURE_VERSION, updated_at=now.isoformat())


def can_order_background(record):
    _open(record)
    if not record["consent_at"]:
        raise VettingError("The background check needs your signed authorization first.")
    if record["background_status"] not in ("not_started",):
        raise VettingError("A background check is already in progress.")


def apply_identity_result(record, verified, now):
    status = "verified" if verified else "failed"
    nxt = dict(record, identity_status=status, updated_at=now.isoformat())
    return _maybe_review(nxt)


def apply_background_result(record, result, report_ref, now):
    if result not in ("clear", "consider", "suspended"):
        raise VettingError(f"Unknown background result {result!r}.")
    nxt = dict(record, background_status=result, report_ref=report_ref, updated_at=now.isoformat())
    return _maybe_review(nxt)


def _maybe_review(record):
    done = record["identity_status"] in ("verified", "failed") and record["background_status"] in ("clear", "consider", "suspended")
    if record["status"] == "applied" and done:
        return dict(record, status="in_review")
    return record


def approve(record, admin, note, now):
    _open(record)
    if record["identity_status"] != "verified":
        raise VettingError("Identity is not verified.")
    if record["background_status"] == "clear":
        pass
    elif record["background_status"] == "consider":
        if len((note or "").strip()) < MIN_NOTE:
            raise VettingError("A 'consider' result needs a written individualized assessment before approval.")
    else:
        raise VettingError("The background check is not finished.")
    return dict(record, status="approved", decided_by=admin, assessment_note=(note or "").strip() or None,
                decision_reason="approved", updated_at=now.isoformat())


def _check_reason(reason, note):
    if reason in FORBIDDEN_REASONS:
        raise VettingError(FORBIDDEN_REASONS[reason])
    if reason not in REASONS:
        raise VettingError("Choose one of the written, job-related criteria.")
    if len((note or "").strip()) < MIN_NOTE:
        raise VettingError("Write the individualized assessment: the offense, how long ago, and why it matters for this work.")


def pre_adverse(record, admin, reason, note, now, wait_days=ADVERSE_WAIT_BUSINESS_DAYS):
    _open(record)
    if record["background_status"] != "consider" or not record["report_ref"]:
        raise VettingError("Pre-adverse action needs a completed report with a 'consider' result.")
    if record["pre_adverse_at"]:
        raise VettingError("Pre-adverse notice was already sent.")
    _check_reason(reason, note)
    return dict(record, status="pre_adverse", pre_adverse_at=now.isoformat(),
                dispute_deadline=add_business_days(now, wait_days).isoformat(), decision_reason=reason,
                assessment_note=note.strip(), decided_by=admin, updated_at=now.isoformat())


def open_dispute(record, now):
    if record["status"] != "pre_adverse":
        raise VettingError("There is no pending decision to dispute.")
    return dict(record, dispute_open=1, updated_at=now.isoformat())


def resolve_dispute(record, admin, now):
    if not record["dispute_open"]:
        raise VettingError("There is no open dispute.")
    return dict(record, dispute_open=0, decided_by=admin, updated_at=now.isoformat())


def final_adverse(record, admin, now):
    if record["status"] != "pre_adverse":
        raise VettingError("Send the pre-adverse notice first.")
    if record["dispute_open"]:
        raise VettingError("The cleaner disputed the report. Resolve the dispute before deciding.")
    if now < datetime.fromisoformat(record["dispute_deadline"]):
        raise VettingError("The waiting period has not ended yet.")
    return dict(record, status="denied", final_adverse_at=now.isoformat(), decided_by=admin, updated_at=now.isoformat())


def decline_identity(record, admin, note, now):
    _open(record)
    if record["identity_status"] != "failed":
        raise VettingError("Only a failed identity check can be declined this way.")
    return dict(record, status="denied", decision_reason="identity_failed", assessment_note=(note or "").strip() or None,
                decided_by=admin, updated_at=now.isoformat())
