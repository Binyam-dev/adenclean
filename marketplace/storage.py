"""Marketplace persistence: four generic row operations on Appwrite tables, with domain
methods on top. Raises store.NotFound / store.Conflict / store.StoreError like the main store.
"""


LIST_CAP = 200


class AppwriteTables:
    """Generic CRUD over Appwrite TablesDB, reusing AppwriteStore's error handling."""

    def __init__(self, appwrite_store):
        self.s = appwrite_store

    def insert(self, table, row):
        self.s._create(table, row["id"], {k: v for k, v in row.items() if k != "id"})

    def get(self, table, row_id):
        row = self.s._call(self.s.db.get_row, table_id=table, row_id=row_id)
        return self.s._row(row)

    def find(self, table, filters, order_desc=None, limit=LIST_CAP):
        Query = self.s.Query
        queries = []
        for key, value in filters.items():
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            queries.append(Query.equal("$id" if key == "id" else key, values))
        if order_desc:
            queries.append(Query.order_desc(order_desc))
        return self.s._list(table, queries, limit=limit)

    def update(self, table, row_id, fields):
        self.s._call(self.s.db.update_row, table_id=table, row_id=row_id, data=dict(fields))


def tables_for(main_store):
    return AppwriteTables(main_store)


class MarketplaceStore:
    """Domain operations. Callers pass ready-made rows; this layer only persists them."""

    def __init__(self, tables):
        self.t = tables

    # users and sign-in
    def create_user(self, row):
        self.t.insert("users", row)

    def get_user(self, user_id):
        return self.t.get("users", user_id)

    def find_user_by_email(self, email):
        rows = self.t.find("users", {"email": email}, limit=1)
        return rows[0] if rows else None

    def update_user(self, user_id, fields):
        self.t.update("users", user_id, fields)

    def add_login_code(self, row):
        self.t.insert("login_codes", row)

    def recent_login_codes(self, email, limit=10):
        return self.t.find("login_codes", {"email": email}, order_desc="created_at", limit=limit)

    def update_login_code(self, code_id, fields):
        self.t.update("login_codes", code_id, fields)

    def add_consent(self, row):
        self.t.insert("consents", row)

    # jobs
    def create_job(self, row):
        self.t.insert("jobs", row)

    def get_job(self, job_id):
        return self.t.get("jobs", job_id)

    def jobs_for_customer(self, customer_id):
        return self.t.find("jobs", {"customer_id": customer_id}, order_desc="created_at")

    def open_jobs_in(self, zips):
        return self.t.find("jobs", {"status": "open", "zip": list(zips)}, order_desc="created_at")

    def update_job(self, job_id, fields):
        self.t.update("jobs", job_id, fields)

    # offers
    def create_offer(self, row):
        self.t.insert("offers", row)

    def get_offer(self, offer_id):
        return self.t.get("offers", offer_id)

    def offers_for_job(self, job_id):
        return self.t.find("offers", {"job_id": job_id}, order_desc="created_at")

    def offers_by_cleaner(self, cleaner_id):
        return self.t.find("offers", {"cleaner_id": cleaner_id}, order_desc="created_at")

    def update_offer(self, offer_id, fields):
        self.t.update("offers", offer_id, fields)

    # bookings and money
    def create_booking(self, row):
        self.t.insert("bookings", row)

    def get_booking(self, booking_id):
        return self.t.get("bookings", booking_id)

    def has_webhook_event(self, event_id):
        return bool(self.t.find("webhook_events", {"id": event_id}, limit=1))

    def booking_for_job(self, job_id):
        rows = self.t.find("bookings", {"job_id": job_id}, limit=1)
        return rows[0] if rows else None

    def booking_by_payment_intent(self, payment_intent_id):
        rows = self.t.find("bookings", {"payment_intent_id": payment_intent_id}, limit=1)
        return rows[0] if rows else None

    def update_booking(self, booking_id, fields):
        self.t.update("bookings", booking_id, fields)

    def bookings_awaiting_release(self):
        return [b for b in self.t.find("bookings", {"payout_status": "none", "payment_status": "paid"})
                if b.get("checked_out_at") and not b.get("confirmed_at")]

    def add_ledger_entry(self, row):
        """Append one entry. Raises store.Conflict if its idempotency key was already used."""
        self.t.insert("ledger_entries", row)

    def ledger_for(self, booking_id):
        return self.t.find("ledger_entries", {"booking_id": booking_id}, order_desc="created_at")

    def payout_account(self, user_id):
        rows = self.t.find("payout_accounts", {"user_id": user_id}, limit=1)
        return rows[0] if rows else None

    def payout_account_by_stripe_id(self, stripe_account_id):
        rows = self.t.find("payout_accounts", {"stripe_account_id": stripe_account_id}, limit=1)
        return rows[0] if rows else None

    def save_payout_account(self, row):
        existing = self.payout_account(row["user_id"])
        if existing:
            self.t.update("payout_accounts", existing["id"], {k: v for k, v in row.items() if k not in ("id", "user_id")})
        else:
            self.t.insert("payout_accounts", row)

    # vetting
    def get_vetting(self, user_id):
        rows = self.t.find("vetting", {"id": user_id}, limit=1)
        return rows[0] if rows else None

    def vetting_by_candidate(self, candidate_ref):
        rows = self.t.find("vetting", {"candidate_ref": candidate_ref}, limit=1)
        return rows[0] if rows else None

    def save_vetting(self, record, created=False):
        if created:
            self.t.insert("vetting", record)
        else:
            self.t.update("vetting", record["id"], {k: v for k, v in record.items() if k != "id"})

    def vetting_queue(self, status):
        return self.t.find("vetting", {"status": status}, order_desc="updated_at")

    # moderation
    def create_report(self, row):
        self.t.insert("reports", row)

    def get_report(self, report_id):
        return self.t.get("reports", report_id)

    def update_report(self, report_id, fields):
        self.t.update("reports", report_id, fields)

    def reports_by_reporter(self, reporter_id):
        return self.t.find("reports", {"reporter_id": reporter_id}, order_desc="created_at")

    def reports_with_status(self, status):
        """Oldest first, so the queue is worked in the order reports arrived."""
        return sorted(self.t.find("reports", {"status": status}), key=lambda r: r["created_at"])

    def reports_about_user(self, user_id):
        return self.t.find("reports", {"target_user_id": user_id}, order_desc="created_at")

    def clear_report_details(self, reporter_id):
        for report in self.reports_by_reporter(reporter_id):
            if report.get("detail"):
                self.t.update("reports", report["id"], {"detail": None})

    def get_block(self, blocker_id, blocked_id):
        rows = self.t.find("blocks", {"blocker_id": blocker_id, "blocked_id": blocked_id}, limit=1)
        return rows[0] if rows else None

    def active_block(self, blocker_id, blocked_id):
        block = self.get_block(blocker_id, blocked_id)
        return block if block and block["active"] else None

    def blocks_by(self, blocker_id):
        return [b for b in self.t.find("blocks", {"blocker_id": blocker_id}, order_desc="created_at") if b["active"]]

    def create_block(self, row):
        self.t.insert("blocks", row)

    def update_block(self, block_id, fields):
        self.t.update("blocks", block_id, fields)

    def get_block_by_id(self, block_id):
        return self.t.get("blocks", block_id)

    def deactivate_blocks_for(self, user_id):
        for key in ("blocker_id", "blocked_id"):
            for block in self.t.find("blocks", {key: user_id}):
                if block["active"]:
                    self.t.update("blocks", block["id"], {"active": 0})

    def record_webhook_event(self, event_id, event_type, received_at):
        """Raises store.Conflict when this event id was already processed."""
        self.t.insert("webhook_events", {"id": event_id, "event_type": event_type, "received_at": received_at})
