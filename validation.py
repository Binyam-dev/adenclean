"""Input validation shared by the public and admin endpoints."""

import re
from datetime import date, datetime

import store as storage

SERVICE_TYPES = {
    "routine": "Routine home cleaning",
    "deep": "Deep cleaning",
    "move-in/move-out": "Move-in / move-out",
    "move-in-move-out": "Move-in / move-out",
    "move-in-out": "Move-in / move-out",
}
PREFERRED_TIMES = {"morning", "afternoon", "flexible"}
RECORD_TYPES = storage.RECORD_TABLES
RECORD_STATUSES = {
    "requests": {"pending", "approved", "declined", "completed", "cancelled"},
    "availability": {"pending", "approved", "declined"},
    "reviews": {"new", "reviewed"},
    "issues": {"open", "in_review", "resolved"},
}
STATUS_TRANSITIONS = {
    "requests": {
        "pending": {"approved", "declined", "cancelled"},
        "approved": {"pending", "completed", "cancelled"},
        "declined": {"pending"},
        "completed": set(),
        "cancelled": {"pending"},
    },
    "availability": {
        "pending": {"approved", "declined"},
        "approved": set(),
        "declined": {"pending"},
    },
    "reviews": {
        "new": {"reviewed"},
        "reviewed": set(),
    },
    "issues": {
        "open": {"in_review", "resolved"},
        "in_review": {"open", "resolved"},
        "resolved": {"in_review"},
    },
}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def clean_text(value, label, max_length, required=True, allow_newlines=False):
    if not isinstance(value, str):
        raise ApiError(400, f"{label} is required.")

    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if allow_newlines:
        value = re.sub(r"[^\S\n]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
    else:
        value = " ".join(value.split())

    value = value.strip()
    if required and not value:
        raise ApiError(400, f"{label} is required.")
    if len(value) > max_length:
        raise ApiError(400, f"{label} must be {max_length} characters or fewer.")
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise ApiError(400, f"{label} contains unsupported characters.")
    return value


def clean_email(value):
    email = clean_text(value, "Email", 254).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
        raise ApiError(400, "Enter a valid email address.")
    return email


def clean_service_type(value):
    service_type = clean_text(value, "Service type", 40).lower().replace("_", "-")
    if service_type not in SERVICE_TYPES:
        raise ApiError(400, "Choose one of the listed service types.")
    return "move-in/move-out" if service_type.startswith("move-in") else service_type


def clean_date(value, label):
    date_value = clean_text(value, label, 10)
    try:
        parsed_date = date.fromisoformat(date_value)
    except ValueError as error:
        raise ApiError(400, f"Choose a valid {label.lower()}.") from error
    if parsed_date < date.today():
        raise ApiError(400, f"{label} must be today or later.")
    return parsed_date.isoformat()


def clean_time(value, label):
    time_value = clean_text(value, label, 5)
    try:
        parsed_time = datetime.strptime(time_value, "%H:%M")
    except ValueError as error:
        raise ApiError(400, f"Choose a valid {label.lower()}.") from error
    return parsed_time.strftime("%H:%M")


def clean_consent(value):
    if value is not True:
        raise ApiError(400, "Please confirm the submission notice.")
    return 1
