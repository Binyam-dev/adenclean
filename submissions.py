"""Public endpoints: service requests, cleaner availability and customer feedback."""

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timezone

import push
from store import Conflict
from validation import (
    PREFERRED_TIMES, ApiError, clean_consent, clean_date, clean_email, clean_service_type,
    clean_text, clean_time,
)


class SubmissionRoutes:
    """Mixin for AdenCleanHandler; reads storage through self.store."""

    def save_service_request(self, payload):
        full_name = clean_text(payload.get("fullName"), "Name", 100)
        email = clean_email(payload.get("email"))
        area = clean_text(payload.get("area"), "Town or postal code", 100)
        service_type = clean_service_type(payload.get("serviceType"))
        preferred_date = clean_date(payload.get("preferredDate"), "Preferred date")
        preferred_time = clean_text(payload.get("preferredTime"), "Preferred time", 20).lower()
        if preferred_time not in PREFERRED_TIMES:
            raise ApiError(400, "Choose a listed preferred time.")
        notes = clean_text(
            payload.get("notes", ""),
            "Notes",
            800,
            required=False,
            allow_newlines=True,
        )
        consent = clean_consent(payload.get("consent"))
        reference = uuid.uuid4().hex[:12].upper()
        feedback_token = secrets.token_urlsafe(32)
        feedback_token_hash = hashlib.sha256(feedback_token.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()

        self.store.add_request(
            {
                "id": reference,
                "created_at": created_at,
                "full_name": full_name,
                "email": email,
                "area": area,
                "service_type": service_type,
                "preferred_date": preferred_date,
                "preferred_time": preferred_time,
                "notes": notes,
                "consent": consent,
                "status": "pending",
                "status_updated_at": created_at,
                "feedback_token_hash": feedback_token_hash,
            },
            {
                "record_type": "requests",
                "record_id": reference,
                "old_status": None,
                "new_status": "pending",
                "note": "Inquiry received.",
                "actor": "system",
                "created_at": created_at,
            },
        )
        return reference, feedback_token

    def handle_customer_feedback(self, payload):
        action = clean_text(payload.get("action"), "Feedback action", 20).lower()
        if action not in {"lookup", "review", "issue"} | push.ACTIONS:
            raise ApiError(400, "Choose a valid feedback action.")

        token = payload.get("token")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ApiError(404, "That private feedback link is invalid.")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        request = self.store.find_request_by_token_hash(token_hash)
        if request is None:
            raise ApiError(404, "That private feedback link is invalid.")
        if action in push.ACTIONS:  # after the private code is proven, so a bad code is always a 404
            return push.handle_action(self.store, request, action, payload)

        review_exists = self.store.get_review_for_request(request["id"]) is not None
        issue = self.store.get_issue_for_request(request["id"])
        issue_exists = issue is not None

        if action == "lookup":
            return 200, {
                "ok": True,
                "ready": request["status"] == "completed",
                "status": request["status"],
                "serviceType": request["service_type"],
                "preferredDate": request["preferred_date"],
                "reviewSubmitted": review_exists,
                "issueSubmitted": issue_exists,
                "issueStatus": issue["status"] if issue else None,
            }

        if request["status"] != "completed":
            raise ApiError(
                409,
                "Feedback is available after AdenClean marks the service complete.",
            )

        consent = clean_consent(payload.get("consent"))
        message = clean_text(
            payload.get("message"),
            "Feedback",
            1200,
            allow_newlines=True,
        )
        if len(message) < 10:
            raise ApiError(400, "Feedback must be at least 10 characters.")

        created_at = datetime.now(timezone.utc).isoformat()
        record_id = uuid.uuid4().hex[:12].upper()
        if action == "review":
            if review_exists:
                raise ApiError(409, "A review has already been submitted for this service.")
            rating = payload.get("rating")
            if isinstance(rating, bool) or not isinstance(rating, int) or rating not in range(1, 6):
                raise ApiError(400, "Choose a rating from 1 to 5.")
            record_status = "new"
            history_type = "reviews"
            history_note = "Customer review received."
            response_message = "Your review was saved for AdenClean to read."
            try:
                self.store.add_review(
                    {
                        "id": record_id,
                        "request_id": request["id"],
                        "created_at": created_at,
                        "rating": rating,
                        "message": message,
                        "consent": consent,
                        "status": "new",
                        "status_updated_at": created_at,
                    },
                    self.feedback_history(history_type, record_id, record_status, history_note, created_at),
                )
            except Conflict as error:
                raise ApiError(409, "A review has already been submitted for this service.") from error
        else:
            if issue_exists:
                raise ApiError(409, "A service issue has already been reported for this request.")
            record_status = "open"
            history_type = "issues"
            history_note = "Customer service issue reported."
            response_message = "Your service issue was sent to AdenClean for review."
            try:
                self.store.add_issue(
                    {
                        "id": record_id,
                        "request_id": request["id"],
                        "created_at": created_at,
                        "message": message,
                        "consent": consent,
                        "status": "open",
                        "status_updated_at": created_at,
                    },
                    self.feedback_history(history_type, record_id, record_status, history_note, created_at),
                )
            except Conflict as error:
                raise ApiError(409, "A service issue has already been reported for this request.") from error

        return 201, {
            "ok": True,
            "kind": action,
            "reference": record_id,
            "message": response_message,
            "reviewSubmitted": review_exists or action == "review",
            "issueSubmitted": issue_exists or action == "issue",
        }

    @staticmethod
    def feedback_history(record_type, record_id, status, note, created_at):
        return {
            "record_type": record_type,
            "record_id": record_id,
            "old_status": None,
            "new_status": status,
            "note": note,
            "actor": "customer",
            "created_at": created_at,
        }

    def save_cleaner_availability(self, payload):
        full_name = clean_text(payload.get("fullName"), "Name", 100)
        email = clean_email(payload.get("email"))
        area = clean_text(payload.get("area"), "Town or postal code", 100)
        service_types = payload.get("serviceTypes")
        if not isinstance(service_types, list) or not service_types or len(service_types) > 3:
            raise ApiError(400, "Choose at least one listed service type.")
        cleaned_service_types = sorted({clean_service_type(value) for value in service_types})
        available_date = clean_date(payload.get("availableDate"), "Available date")
        start_time = clean_time(payload.get("startTime"), "Start time")
        end_time = clean_time(payload.get("endTime"), "End time")
        if end_time <= start_time:
            raise ApiError(400, "End time must be later than start time.")
        consent = clean_consent(payload.get("consent"))
        reference = uuid.uuid4().hex[:12].upper()
        created_at = datetime.now(timezone.utc).isoformat()

        self.store.add_availability(
            {
                "id": reference,
                "created_at": created_at,
                "full_name": full_name,
                "email": email,
                "area": area,
                "service_types": json.dumps(cleaned_service_types),
                "available_date": available_date,
                "start_time": start_time,
                "end_time": end_time,
                "consent": consent,
                "status": "pending",
                "status_updated_at": created_at,
            },
            {
                "record_type": "availability",
                "record_id": reference,
                "old_status": None,
                "new_status": "pending",
                "note": "Availability received.",
                "actor": "system",
                "created_at": created_at,
            },
        )
        return reference

