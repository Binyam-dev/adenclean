"""Marketplace persistence: four generic operations per backend, domain methods on top.

Both adapters raise store.NotFound / store.Conflict / store.StoreError like the main store.
"""

import sqlite3
from contextlib import closing

import store as base

from .schema import INTEGER, MARKETPLACE_SCHEMA

LIST_CAP = 200


class SqliteTables:
    """Generic CRUD over the marketplace tables in the existing SQLite file."""

    def __init__(self, sqlite_store):
        self._connect = sqlite_store._connect
        statements = []
        for table, spec in MARKETPLACE_SCHEMA.items():
            cols = ", ".join(
                f"{key} {'INTEGER' if kind == INTEGER else 'TEXT'}{' NOT NULL' if required else ''}"
                for key, kind, _size, required in spec["columns"]
            )
            statements.append(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, {cols});")
            for name, kind, columns in spec["indexes"]:
                unique = "UNIQUE " if kind == "unique" else ""
                statements.append(
                    f"CREATE {unique}INDEX IF NOT EXISTS {table}_{name} ON {table}({', '.join(columns)});"
                )
        try:
            with closing(self._connect()) as connection, connection:
                connection.executescript("\n".join(statements))
        except sqlite3.Error as error:
            raise base.StoreError("Could not prepare marketplace tables.") from error

    def insert(self, table, row):
        keys = list(row)
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
                    tuple(row[k] for k in keys),
                )
        except sqlite3.IntegrityError as error:
            raise base.Conflict("That record already exists.") from error
        except sqlite3.Error as error:
            raise base.StoreError("Database write failed.") from error

    def get(self, table, row_id):
        rows = self.find(table, {"id": row_id}, limit=1)
        if not rows:
            raise base.NotFound("That record could not be found.")
        return rows[0]

    def find(self, table, filters, order_desc=None, limit=LIST_CAP):
        where, params = [], []
        for key, value in filters.items():
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            where.append(f"{key} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        sql = f"SELECT * FROM {table}" + (f" WHERE {' AND '.join(where)}" if where else "")
        if order_desc:
            sql += f" ORDER BY {order_desc} DESC"
        sql += f" LIMIT {int(limit)}"
        try:
            with closing(self._connect()) as connection:
                return [dict(row) for row in connection.execute(sql, params)]
        except sqlite3.Error as error:
            raise base.StoreError("Database read failed.") from error

    def update(self, table, row_id, fields):
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                    (*fields.values(), row_id),
                )
                if cursor.rowcount == 0:
                    raise base.NotFound("That record could not be found.")
        except sqlite3.IntegrityError as error:
            raise base.Conflict("That record already exists.") from error
        except sqlite3.Error as error:
            raise base.StoreError("Database write failed.") from error


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
    if main_store.name == "sqlite":
        return SqliteTables(main_store)
    if main_store.name == "appwrite":
        return AppwriteTables(main_store)
    raise RuntimeError(f"No marketplace adapter for {main_store.name}")


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

    def record_webhook_event(self, event_id, event_type, received_at):
        """Raises store.Conflict when this event id was already processed."""
        self.t.insert("webhook_events", {"id": event_id, "event_type": event_type, "received_at": received_at})
