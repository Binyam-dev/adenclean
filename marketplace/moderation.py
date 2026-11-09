"""Report and block rules (Apple guideline 1.2). Pure functions plus small store lookups.

The text filter is a speed bump, not a guarantee: it misses things and can block innocent
text. Reports are the backstop. The abusive-word list is data, owned and reviewed by the owner.
"""

import re
from datetime import datetime, timedelta

REASONS = {
    "spam": "Spam or an unwanted offer",
    "harassment": "Harassment or abuse",
    "unsafe": "Unsafe or threatening",
    "off_platform": "Asks to pay or talk outside AdenClean",
    "fake": "Fake or misleading",
    "other": "Something else",
}
REPORT_TARGETS = ("job", "offer")
REPORTS_PER_HOUR = 10
ACTIVE_BOOKING_JOB_STATUSES = ("booked", "in_progress", "awaiting_confirmation", "disputed")

# Whole words, lowercase. Short on purpose; the owner adds to it. Slurs are intentionally
# left for the owner to add after reviewing what the reports show. This is a cleaning
# marketplace, so words that are normal in the work must NOT be here: "trash", "soap scum",
# "pet piss", "kill the mold", "crap" on a floor. Threats are left to reports, not word matching.
ABUSIVE_TERMS = frozenset("""
fuck fucker fucking motherfucker shit shitty bitch bastard asshole dickhead cunt slut whore
douchebag moron idiot stupid rape
""".split())

# 10+ digits in a phone-like shape (optional +1, optional brackets, separators). Plain numbers
# such as ZIP codes, street numbers, times and gate codes have fewer digits and pass.
_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+\s*(?:@|\(at\)|\[at\])\s*[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)
_LINK = re.compile(
    r"(?:https?://|www\.)\S+|\b[a-z0-9][a-z0-9\-]*\.(?:com|net|org|io|co|me|us|app|info|biz|ly|gg)\b", re.I)
_WORD = re.compile(r"[a-z']+")


class ModerationError(ValueError):
    pass


def check_text(text):
    """Return None if the text is fine, else 'contact' or 'abusive'."""
    if not text:
        return None
    if _PHONE.search(text) or _EMAIL.search(text) or _LINK.search(text):
        return "contact"
    if any(word.strip("'") in ABUSIVE_TERMS for word in _WORD.findall(text.lower())):
        return "abusive"
    return None


FILTER_MESSAGES = {
    "contact": "Please remove phone numbers, email addresses and links from {field}. "
               "Keep contact details inside AdenClean.",
    "abusive": "Please remove rude or threatening words from {field}.",
}


def filter_message(reason, field):
    return FILTER_MESSAGES[reason].format(field=field)


def clean_reason(value):
    if value not in REASONS:
        raise ModerationError("Choose a reason from the list.")
    return value


def reports_left(market, reporter_id, now):
    """How many new reports this person may still file this hour (counted from stored rows)."""
    cutoff = (now - timedelta(hours=1)).isoformat()
    recent = [r for r in market.reports_by_reporter(reporter_id) if r["created_at"] >= cutoff]
    return max(0, REPORTS_PER_HOUR - len(recent))


def pair_blocked(market, a, b):
    """True when either person has an active block on the other."""
    return market.active_block(a, b) is not None or market.active_block(b, a) is not None


def hidden_between(market, a, b, job_id=None):
    """Jobs and offers are hidden between a blocked pair, except the one job they are booked
    on (so a live booking can finish). A block never lets the blocked person bid on or see the
    blocker's other jobs, even while a booking runs."""
    if not pair_blocked(market, a, b):
        return False
    if job_id is not None:
        booking = market.booking_for_job(job_id)
        if booking and not booking.get("cancelled_by") and {booking["customer_id"], booking["cleaner_id"]} == {a, b}:
            return False
    return True
