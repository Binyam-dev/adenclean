"""Marketplace tables, in the same shape as store.APPWRITE_SCHEMA.

store.py merges these into APPWRITE_SCHEMA, so setup_appwrite.py provisions them and the
test fake enforces their unique indexes. All rows are server-only (permissions=[]).
Exact street addresses are not stored in Phase 1; jobs carry only a ZIP code.
"""

VARCHAR, TEXT, INTEGER = "varchar", "text", "integer"

MARKETPLACE_SCHEMA = {
    "users": {
        "columns": [
            ("email", VARCHAR, 254, True),
            ("display_name", VARCHAR, 80, True),
            ("roles", VARCHAR, 80, True),  # comma list: customer, cleaner
            ("status", VARCHAR, 20, True),  # active | suspended | deleted
            ("home_zip", VARCHAR, 10, False),
            ("language_codes", VARCHAR, 60, False),
            ("created_at", VARCHAR, 40, True),
            ("deleted_at", VARCHAR, 40, False),
        ],
        "indexes": [("uniq_email", "unique", ["email"]), ("idx_status", "key", ["status"])],
    },
    "login_codes": {
        "columns": [
            ("email", VARCHAR, 254, True),
            ("code_hash", VARCHAR, 64, True),
            ("created_at", VARCHAR, 40, True),
            ("expires_at", VARCHAR, 40, True),
            ("attempts", INTEGER, None, True),
            ("used", INTEGER, None, True),
        ],
        "indexes": [("idx_email", "key", ["email"]), ("idx_created", "key", ["created_at"])],
    },
    "jobs": {
        "columns": [
            ("customer_id", VARCHAR, 36, True),
            ("status", VARCHAR, 30, True),
            ("service_type", VARCHAR, 40, True),
            ("zip", VARCHAR, 10, True),
            ("bedrooms", INTEGER, None, True),
            ("bathrooms", INTEGER, None, True),
            ("supplies", VARCHAR, 20, True),  # customer | cleaner
            ("date_from", VARCHAR, 10, True),
            ("date_to", VARCHAR, 10, True),
            ("budget_cents", INTEGER, None, False),
            ("notes", TEXT, None, False),
            ("booked_offer_id", VARCHAR, 36, False),
            ("price_cents", INTEGER, None, False),
            ("created_at", VARCHAR, 40, True),
            ("expires_at", VARCHAR, 40, True),
            ("status_updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("idx_customer", "key", ["customer_id"]),
            ("idx_status", "key", ["status"]),
            ("idx_zip", "key", ["zip"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "offers": {
        "columns": [
            ("job_id", VARCHAR, 36, True),
            ("cleaner_id", VARCHAR, 36, True),
            ("price_cents", INTEGER, None, True),
            ("status", VARCHAR, 20, True),
            ("counter_rounds", INTEGER, None, True),
            ("awaiting", VARCHAR, 20, True),
            ("message", VARCHAR, 500, False),
            ("flags", VARCHAR, 120, False),
            ("created_at", VARCHAR, 40, True),
            ("expires_at", VARCHAR, 40, True),
            ("updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("uniq_job_cleaner", "unique", ["job_id", "cleaner_id"]),  # one offer per cleaner per job
            ("idx_job", "key", ["job_id"]),
            ("idx_cleaner", "key", ["cleaner_id"]),
            ("idx_status", "key", ["status"]),
        ],
    },
    "consents": {
        "columns": [
            ("user_id", VARCHAR, 36, True),
            ("kind", VARCHAR, 40, True),  # terms | privacy | background_check
            ("version", VARCHAR, 20, True),
            ("ip", VARCHAR, 64, False),
            ("created_at", VARCHAR, 40, True),
        ],
        "indexes": [("idx_user", "key", ["user_id"])],
    },
    # -- Phase 2: money ------------------------------------------------------------
    "bookings": {
        "columns": [
            ("job_id", VARCHAR, 36, True),
            ("offer_id", VARCHAR, 36, True),
            ("customer_id", VARCHAR, 36, True),
            ("cleaner_id", VARCHAR, 36, True),
            ("price_cents", INTEGER, None, True),
            ("fee_bps", INTEGER, None, True),  # fee rate frozen at booking time
            ("tip_cents", INTEGER, None, True),
            ("payment_status", VARCHAR, 20, True),  # unpaid | paid | refunded
            ("payment_intent_id", VARCHAR, 80, False),
            ("charge_id", VARCHAR, 80, False),
            ("payout_status", VARCHAR, 20, True),  # none | sent
            ("starts_on", VARCHAR, 10, True),
            ("checked_in_at", VARCHAR, 40, False),
            ("checked_out_at", VARCHAR, 40, False),
            ("confirmed_at", VARCHAR, 40, False),
            ("cancelled_by", VARCHAR, 20, False),
            ("created_at", VARCHAR, 40, True),
            ("updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("uniq_job", "unique", ["job_id"]),  # one booking per job
            ("idx_customer", "key", ["customer_id"]),
            ("idx_cleaner", "key", ["cleaner_id"]),
            ("idx_pi", "key", ["payment_intent_id"]),
        ],
    },
    "ledger_entries": {  # append-only; never updated or deleted
        "columns": [
            ("booking_id", VARCHAR, 36, True),
            ("entry_type", VARCHAR, 30, True),  # charge | tip_charge | refund | transfer
            ("amount_cents", INTEGER, None, True),
            ("direction", VARCHAR, 4, True),  # in (to the platform) | out
            ("stripe_ref", VARCHAR, 80, False),
            ("idempotency_key", VARCHAR, 120, True),
            ("created_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("uniq_idem", "unique", ["idempotency_key"]),
            ("idx_booking", "key", ["booking_id"]),
        ],
    },
    "payout_accounts": {
        "columns": [
            ("user_id", VARCHAR, 36, True),
            ("stripe_account_id", VARCHAR, 80, True),
            ("payouts_enabled", INTEGER, None, True),
            ("updated_at", VARCHAR, 40, True),
        ],
        "indexes": [("uniq_user", "unique", ["user_id"]), ("idx_account", "key", ["stripe_account_id"])],
    },
    "webhook_events": {  # row id is the Stripe event id, so a replay is a Conflict
        "columns": [
            ("event_type", VARCHAR, 80, True),
            ("received_at", VARCHAR, 40, True),
        ],
        "indexes": [],
    },
    # -- Phase 2: vetting (row id = the cleaner's user id; no report contents stored) ------
    "vetting": {
        "columns": [
            ("status", VARCHAR, 20, True),  # applied | in_review | pre_adverse | approved | denied
            ("consent_at", VARCHAR, 40, False),
            ("consent_name", VARCHAR, 120, False),
            ("disclosure_version", VARCHAR, 20, False),
            ("identity_status", VARCHAR, 20, True),
            ("identity_ref", VARCHAR, 80, False),
            ("background_status", VARCHAR, 20, True),
            ("candidate_ref", VARCHAR, 80, False),
            ("report_ref", VARCHAR, 80, False),
            ("pre_adverse_at", VARCHAR, 40, False),
            ("dispute_deadline", VARCHAR, 40, False),
            ("dispute_open", INTEGER, None, True),
            ("final_adverse_at", VARCHAR, 40, False),
            ("decision_reason", VARCHAR, 40, False),
            ("assessment_note", TEXT, None, False),
            ("decided_by", VARCHAR, 254, False),
            ("created_at", VARCHAR, 40, True),
            ("updated_at", VARCHAR, 40, True),
        ],
        "indexes": [("idx_status", "key", ["status"]), ("idx_candidate", "key", ["candidate_ref"])],
    },
}
