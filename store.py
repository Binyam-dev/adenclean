"""Storage backends for AdenClean.

``AppwriteStore`` is the only store. It talks to Appwrite TablesDB through a server API
key that is limited to reading and writing rows.

``open_store()`` picks where the tables live:

* ``ADENCLEAN_STORAGE=appwrite`` (the default) - the real Appwrite project. The app refuses
  to start if the Appwrite settings are missing, so a typo cannot lose customer data.
* ``ADENCLEAN_STORAGE=memory`` - in-memory tables for local development and tests. Nothing
  is saved; it is refused on Render.
"""

import logging
import os
import threading
import uuid

log = logging.getLogger("adenclean.store")

RECORD_TABLES = {
    "requests": "customer_requests",
    "availability": "cleaner_availability",
    "reviews": "customer_reviews",
    "issues": "service_issues",
}
# Fields the admin list returns for each record type (no consent flag, no token hash).
LIST_FIELDS = {
    "requests": (
        "id", "created_at", "full_name", "email", "area", "service_type",
        "preferred_date", "preferred_time", "notes", "status", "status_updated_at",
    ),
    "availability": (
        "id", "created_at", "full_name", "email", "area", "service_types",
        "available_date", "start_time", "end_time", "status", "status_updated_at",
    ),
    "reviews": (
        "id", "request_id", "created_at", "rating", "message", "status",
        "status_updated_at",
    ),
    "issues": (
        "id", "request_id", "created_at", "message", "status", "status_updated_at",
    ),
}
# Reviews and issues also show who the original request came from.
REQUEST_JOIN_FIELDS = ("full_name", "email", "area", "service_type", "preferred_date")
LIST_LIMIT = 100

VARCHAR, TEXT, INTEGER = "varchar", "text", "integer"
# table -> columns (key, kind, size, required) and indexes (key, type, [columns]).
# Rows are addressed by the Appwrite row id, so there is no ``id`` column.
APPWRITE_SCHEMA = {
    "customer_requests": {
        "columns": [
            ("created_at", VARCHAR, 40, True),
            ("full_name", VARCHAR, 100, True),
            ("email", VARCHAR, 254, True),
            ("area", VARCHAR, 100, True),
            ("service_type", VARCHAR, 40, True),
            ("preferred_date", VARCHAR, 10, True),
            ("preferred_time", VARCHAR, 20, True),
            ("notes", TEXT, None, False),
            ("consent", INTEGER, None, True),
            ("status", VARCHAR, 20, True),
            ("status_updated_at", VARCHAR, 40, True),
            ("feedback_token_hash", VARCHAR, 64, True),
        ],
        "indexes": [
            ("uniq_feedback_token", "unique", ["feedback_token_hash"]),
            ("idx_status", "key", ["status"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "cleaner_availability": {
        "columns": [
            ("created_at", VARCHAR, 40, True),
            ("full_name", VARCHAR, 100, True),
            ("email", VARCHAR, 254, True),
            ("area", VARCHAR, 100, True),
            ("service_types", TEXT, None, True),
            ("available_date", VARCHAR, 10, True),
            ("start_time", VARCHAR, 5, True),
            ("end_time", VARCHAR, 5, True),
            ("consent", INTEGER, None, True),
            ("status", VARCHAR, 20, True),
            ("status_updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("idx_status", "key", ["status"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "status_history": {
        "columns": [
            ("record_type", VARCHAR, 20, True),
            ("record_id", VARCHAR, 36, True),
            ("old_status", VARCHAR, 20, False),
            ("new_status", VARCHAR, 20, True),
            ("note", VARCHAR, 240, False),
            ("actor", VARCHAR, 254, True),
            ("created_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("idx_record", "key", ["record_type", "record_id"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "customer_reviews": {
        "columns": [
            ("request_id", VARCHAR, 36, True),
            ("created_at", VARCHAR, 40, True),
            ("rating", INTEGER, None, True),
            ("message", TEXT, None, True),
            ("consent", INTEGER, None, True),
            ("status", VARCHAR, 20, True),
            ("status_updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("uniq_request", "unique", ["request_id"]),
            ("idx_status", "key", ["status"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "service_issues": {
        "columns": [
            ("request_id", VARCHAR, 36, True),
            ("created_at", VARCHAR, 40, True),
            ("message", TEXT, None, True),
            ("consent", INTEGER, None, True),
            ("status", VARCHAR, 20, True),
            ("status_updated_at", VARCHAR, 40, True),
        ],
        "indexes": [
            ("uniq_request", "unique", ["request_id"]),
            ("idx_status", "key", ["status"]),
            ("idx_created", "key", ["created_at"]),
        ],
    },
    "admins": {
        "columns": [
            ("email", VARCHAR, 190, True),
            ("password_hash", VARCHAR, 300, True),
            ("role", VARCHAR, 20, True),
            ("active", INTEGER, None, True),
            ("created_at", VARCHAR, 40, True),
        ],
        "indexes": [("uniq_email", "unique", ["email"])],
    },
}
from marketplace.schema import MARKETPLACE_SCHEMA  # noqa: E402

APPWRITE_SCHEMA.update(MARKETPLACE_SCHEMA)
# Tables included in backup exports. Admin password hashes are deliberately left out.
# Marketplace tables join this list once production has them (setup_appwrite.py), so the
# nightly backup never fails on a table that does not exist yet.
EXPORT_TABLES = (
    "customer_requests", "cleaner_availability", "status_history",
    "customer_reviews", "service_issues",
)


class StoreError(Exception):
    """The storage backend failed. Safe to show a generic message to users."""


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


def _project(row, fields):
    return {field: row.get(field) for field in fields}


def _blank_none(record):
    for key in ("notes", "preferred_time", "area"):
        if key in record and record[key] is None:
            record[key] = ""
    return record


def _new_row_id():
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Appwrite (production)
# ---------------------------------------------------------------------------

class AppwriteStore:
    name = "appwrite"
    PAGE = 100

    def __init__(self, endpoint, project_id, api_key, database_id, tables_db=None):
        from appwrite.query import Query

        self.Query = Query
        self.database_id = database_id
        # Appwrite has no conditional update. One process-wide lock makes the
        # read-check-write in set_status safe for a single app process.
        self._lock = threading.Lock()
        if tables_db is None:
            from appwrite.client import Client
            from appwrite.services.tables_db import TablesDB

            client = Client().set_endpoint(endpoint).set_project(project_id).set_key(api_key)
            tables_db = TablesDB(client)
        self.db = tables_db

    def init(self):
        """Nothing to do: tables are created once with setup_appwrite.py."""

    # -- plumbing ---------------------------------------------------------------

    def _call(self, function, **kwargs):
        try:
            return function(database_id=self.database_id, **kwargs)
        except Exception as error:  # SDK exceptions and network failures alike
            code = getattr(error, "code", 0)
            if code == 404:
                raise NotFound("That record could not be found.") from error
            if code == 409:
                raise Conflict("That record already exists.") from error
            log.error(
                "Appwrite call failed (code=%s type=%s)", code, getattr(error, "type", None)
            )
            raise StoreError("Storage request failed.") from error

    @staticmethod
    def _row(row):
        record = dict(row.data)
        record["id"] = row.id
        return record

    def _list(self, table, queries, limit=None):
        """List rows, following cursors in pages of 100. ``limit`` caps the total."""
        Query = self.Query
        # Callers never pass their own limit query: exactly one is sent per request.
        page_size = min(self.PAGE, limit) if limit is not None else self.PAGE
        rows, cursor = [], None
        while True:
            page_queries = list(queries) + [Query.limit(page_size)]
            if cursor:
                page_queries.append(Query.cursor_after(cursor))
            result = self._call(self.db.list_rows, table_id=table, queries=page_queries)
            batch = list(result.rows)
            rows.extend(batch)
            if len(batch) < page_size or (limit is not None and len(rows) >= limit):
                break
            cursor = batch[-1].id
        rows = rows[:limit] if limit is not None else rows
        return [self._row(row) for row in rows]

    def _find_one(self, table, attribute, value):
        Query = self.Query
        rows = self._list(table, [Query.equal(attribute, value)], limit=1)
        return rows[0] if rows else None

    def _create(self, table, row_id, data):
        self._call(
            self.db.create_row, table_id=table, row_id=row_id, data=data, permissions=[]
        )

    def _write_history(self, history):
        data = {
            "record_type": history["record_type"],
            "record_id": history["record_id"],
            "old_status": history.get("old_status"),
            "new_status": history["new_status"],
            "note": history.get("note", ""),
            "actor": history["actor"],
            "created_at": history["created_at"],
        }
        try:
            self._create("status_history", _new_row_id(), data)
        except StoreError:
            # The record itself is saved; losing one history line must not fail the user.
            log.error("Could not write status history for %s", history["record_id"])

    def _add(self, table, row, history):
        data = {key: value for key, value in row.items() if key != "id"}
        self._create(table, row["id"], data)
        self._write_history(history)

    # -- customer requests / availability ----------------------------------

    def add_request(self, row, history):
        self._add("customer_requests", row, history)

    def add_availability(self, row, history):
        self._add("cleaner_availability", row, history)

    def find_request_by_token_hash(self, token_hash):
        return self._find_one("customer_requests", "feedback_token_hash", token_hash)

    # -- feedback -----------------------------------------------------------

    def get_review_for_request(self, request_id):
        return self._find_one("customer_reviews", "request_id", request_id)

    def get_issue_for_request(self, request_id):
        return self._find_one("service_issues", "request_id", request_id)

    def add_review(self, row, history):
        self._add("customer_reviews", row, history)

    def add_issue(self, row, history):
        self._add("service_issues", row, history)

    # -- admin review ---------------------------------------------------------

    def get_status(self, record_type, record_id):
        row = self._call(
            self.db.get_row, table_id=RECORD_TABLES[record_type], row_id=record_id
        )
        return row.data["status"]

    def set_status(self, record_type, record_id, expected_status, new_status, changed_at, history):
        table = RECORD_TABLES[record_type]
        with self._lock:
            row = self._call(self.db.get_row, table_id=table, row_id=record_id)
            if row.data["status"] != expected_status:
                raise Conflict("This record changed.")
            self._call(
                self.db.update_row,
                table_id=table,
                row_id=record_id,
                data={"status": new_status, "status_updated_at": changed_at},
            )
        self._write_history(history)

    def _count(self, table, status):
        Query = self.Query
        result = self._call(
            self.db.list_rows,
            table_id=table,
            queries=[Query.equal("status", status), Query.limit(1)],
        )
        return int(result.total)

    def list_records(self, record_type, status_filter, statuses):
        Query = self.Query
        table = RECORD_TABLES[record_type]
        queries = [Query.order_desc("created_at")]
        if status_filter != "all":
            queries.append(Query.equal("status", status_filter))
        rows = self._list(table, queries, limit=LIST_LIMIT)

        records = []
        if record_type in ("requests", "availability"):
            for row in rows:
                records.append(_blank_none(_project(row, LIST_FIELDS[record_type])))
        else:
            request_ids = sorted({row["request_id"] for row in rows})
            requests = {}
            for start in range(0, len(request_ids), self.PAGE):
                chunk = request_ids[start:start + self.PAGE]
                for request in self._list(
                    "customer_requests", [Query.equal("$id", chunk)]
                ):
                    requests[request["id"]] = request
            for row in rows:
                request = requests.get(row["request_id"])
                if request is None:  # feedback whose request is gone is not listed
                    continue
                record = _project(row, LIST_FIELDS[record_type])
                record.update(_project(request, REQUEST_JOIN_FIELDS))
                records.append(record)

        counts = {status: self._count(table, status) for status in statuses}
        histories = {record["id"]: [] for record in records}
        ids = list(histories)
        for start in range(0, len(ids), self.PAGE):
            chunk = ids[start:start + self.PAGE]
            for row in self._list(
                "status_history",
                [
                    Query.equal("record_type", record_type),
                    Query.equal("record_id", chunk),
                    Query.order_asc("created_at"),
                ],
            ):
                histories[row["record_id"]].append(
                    {
                        "record_id": row["record_id"],
                        "old_status": row.get("old_status"),
                        "new_status": row["new_status"],
                        "note": row.get("note") or "",
                        "actor": row["actor"],
                        "created_at": row["created_at"],
                    }
                )
        return records, counts, histories

    # -- admin accounts -----------------------------------------------------

    def has_admins(self):
        Query = self.Query
        rows = self._list("admins", [Query.equal("active", 1)], limit=1)
        return bool(rows)

    def get_admin_by_email(self, email):
        return self._find_one("admins", "email", email)

    def get_admin(self, admin_id):
        try:
            row = self._call(self.db.get_row, table_id="admins", row_id=admin_id)
        except NotFound:
            return None
        return self._row(row)

    def add_admin(self, row):
        data = {key: value for key, value in row.items() if key != "id"}
        try:
            self._create("admins", row["id"], data)
        except Conflict as error:
            raise Conflict("An admin with that email already exists.") from error

    def list_admins(self):
        rows = self._list("admins", [self.Query.order_asc("created_at")])
        return [
            {key: row.get(key) for key in ("id", "email", "role", "active", "created_at")}
            for row in rows
        ]

    def set_admin_active(self, email, active):
        admin = self.get_admin_by_email(email)
        if admin is None:
            raise NotFound("No admin with that email.")
        self._call(
            self.db.update_row,
            table_id="admins",
            row_id=admin["id"],
            data={"active": 1 if active else 0},
        )

    # -- backup ----------------------------------------------------------------

    def export_all(self):
        return {table: self._list(table, []) for table in EXPORT_TABLES}


# ---------------------------------------------------------------------------

def open_store(environ=None):
    environ = os.environ if environ is None else environ
    mode = environ.get("ADENCLEAN_STORAGE", "appwrite").strip().lower()
    if mode == "memory":
        if environ.get("RENDER"):
            raise RuntimeError("ADENCLEAN_STORAGE=memory is for local development only; it saves nothing.")
        from memory_tables import MemoryTablesDB

        opened = AppwriteStore("", "", "", "adenclean", tables_db=MemoryTablesDB())
        opened.name = "memory"
        return opened
    if mode == "appwrite":
        missing = [
            name
            for name in ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_API_KEY")
            if not environ.get(name)
        ]
        if missing:
            raise RuntimeError(
                "ADENCLEAN_STORAGE=appwrite but these settings are missing: " + ", ".join(missing)
            )
        return AppwriteStore(
            environ["APPWRITE_ENDPOINT"],
            environ["APPWRITE_PROJECT_ID"],
            environ["APPWRITE_API_KEY"],
            environ.get("APPWRITE_DATABASE_ID", "adenclean"),
        )
    raise RuntimeError("ADENCLEAN_STORAGE must be 'appwrite' or 'memory'.")
