"""An in-memory stand-in for Appwrite's TablesDB, for local development and tests.

Nothing is written to disk: data is lost when the process stops. Production always
uses the real Appwrite service (see store.open_store).

Every call is first checked against the REAL SDK method signature (names and
required arguments), so a misspelled keyword fails here instead of against the live
service. It understands the Query methods AdenClean uses (equal, orderAsc/Desc,
limit, cursorAfter), rejects repeated limits, and enforces the unique indexes
declared in APPWRITE_SCHEMA.
"""

import inspect
import json
from types import SimpleNamespace

from appwrite.enums.column_status import ColumnStatus
from appwrite.enums.tables_db_index_type import TablesDBIndexType
from appwrite.exception import AppwriteException
from appwrite.services.tables_db import TablesDB

import store as storage


def _check_signature(name, kwargs):
    # Raises TypeError for unknown or missing arguments, exactly like a real call would.
    inspect.signature(getattr(TablesDB, name)).bind(None, **kwargs)


def _not_found(what):
    return AppwriteException(f"{what} not found", 404, "not_found")


class MemoryTablesDB:
    def __init__(self, provisioned=True):
        self.databases = {"adenclean"} if provisioned else set()
        self.tables = {}  # table_id -> {"columns": {key: kind}, "indexes": {key: (type, cols)}, "rows": {}}
        self.table_permissions = {}
        self.calls = []
        if provisioned:
            for table_id, spec in storage.APPWRITE_SCHEMA.items():
                self.tables[table_id] = {
                    "columns": {c[0]: c[1] for c in spec["columns"]},
                    "indexes": {i[0]: (i[1], i[2]) for i in spec["indexes"]},
                    "rows": {},
                }

    # -- schema management (used by setup_appwrite.py) ----------------------------

    def get(self, **kw):
        _check_signature("get", kw)
        if kw["database_id"] not in self.databases:
            raise _not_found("database")
        return SimpleNamespace(id=kw["database_id"])

    def create(self, **kw):
        _check_signature("create", kw)
        self.calls.append(("create_database", kw["database_id"]))
        self.databases.add(kw["database_id"])
        return SimpleNamespace(id=kw["database_id"])

    def _db(self, kw):
        if kw["database_id"] not in self.databases:
            raise _not_found("database")

    def get_table(self, **kw):
        _check_signature("get_table", kw)
        self._db(kw)
        if kw["table_id"] not in self.tables:
            raise _not_found("table")
        return SimpleNamespace(id=kw["table_id"])

    def create_table(self, **kw):
        _check_signature("create_table", kw)
        self._db(kw)
        self.calls.append(("create_table", kw["table_id"]))
        self.table_permissions[kw["table_id"]] = (kw.get("permissions"), kw.get("row_security"))
        self.tables[kw["table_id"]] = {"columns": {}, "indexes": {}, "rows": {}}
        return SimpleNamespace(id=kw["table_id"])

    def list_columns(self, **kw):
        _check_signature("list_columns", kw)
        table = self._table(kw["table_id"])
        columns = [
            SimpleNamespace(key=key, status=ColumnStatus.AVAILABLE) for key in table["columns"]
        ]
        return SimpleNamespace(columns=columns, total=len(columns))

    def _add_column(self, name, kw, kind):
        _check_signature(name, kw)
        self.calls.append(("create_column", kw["table_id"], kw["key"]))
        self._table(kw["table_id"])["columns"][kw["key"]] = kind
        return SimpleNamespace(key=kw["key"])

    def create_varchar_column(self, **kw):
        return self._add_column("create_varchar_column", kw, "varchar")

    def create_text_column(self, **kw):
        return self._add_column("create_text_column", kw, "text")

    def create_integer_column(self, **kw):
        return self._add_column("create_integer_column", kw, "integer")

    def list_indexes(self, **kw):
        _check_signature("list_indexes", kw)
        table = self._table(kw["table_id"])
        indexes = [SimpleNamespace(key=key) for key in table["indexes"]]
        return SimpleNamespace(indexes=indexes, total=len(indexes))

    def create_index(self, **kw):
        _check_signature("create_index", kw)
        if not isinstance(kw["type"], TablesDBIndexType):
            raise AppwriteException("bad index type", 400, "general_argument_invalid")
        table = self._table(kw["table_id"])
        missing = [c for c in kw["columns"] if c not in table["columns"]]
        if missing:
            raise AppwriteException(f"unknown columns {missing}", 400, "column_not_found")
        self.calls.append(("create_index", kw["table_id"], kw["key"]))
        table["indexes"][kw["key"]] = (kw["type"].value, kw["columns"])
        return SimpleNamespace(key=kw["key"])

    # -- rows ------------------------------------------------------------------------

    def _table(self, table_id):
        if table_id not in self.tables:
            raise _not_found("table")
        return self.tables[table_id]

    def create_row(self, **kw):
        _check_signature("create_row", kw)
        self.calls.append(("create_row", kw["table_id"], kw.get("permissions")))
        table = self._table(kw["table_id"])
        row_id, data = kw["row_id"], kw["data"]
        if row_id in table["rows"]:
            raise AppwriteException("exists", 409, "row_already_exists")
        for _key, kind, columns in (
            (i[0], i[1], i[2]) for i in storage.APPWRITE_SCHEMA[kw["table_id"]]["indexes"]
        ):
            if kind != "unique":
                continue
            value = tuple(data.get(c) for c in columns)
            if any(tuple(r.get(c) for c in columns) == value for r in table["rows"].values()):
                raise AppwriteException("duplicate", 409, "row_already_exists")
        for column, _kind, _size, required in storage.APPWRITE_SCHEMA[kw["table_id"]]["columns"]:
            if required and data.get(column) is None:
                raise AppwriteException(f"missing {column}", 400, "document_invalid_structure")
        table["rows"][row_id] = dict(data)
        return self._row(row_id, table["rows"][row_id])

    def get_row(self, **kw):
        _check_signature("get_row", kw)
        table = self._table(kw["table_id"])
        if kw["row_id"] not in table["rows"]:
            raise AppwriteException("not found", 404, "row_not_found")
        return self._row(kw["row_id"], table["rows"][kw["row_id"]])

    def update_row(self, **kw):
        _check_signature("update_row", kw)
        table = self._table(kw["table_id"])
        if kw["row_id"] not in table["rows"]:
            raise AppwriteException("not found", 404, "row_not_found")
        table["rows"][kw["row_id"]].update(kw.get("data") or {})
        return self._row(kw["row_id"], table["rows"][kw["row_id"]])

    def list_rows(self, **kw):
        _check_signature("list_rows", kw)
        rows = [(rid, dict(d)) for rid, d in self._table(kw["table_id"])["rows"].items()]
        limit, cursor, orders, limits_seen = 25, None, [], 0
        for raw in kw.get("queries") or []:
            query = json.loads(raw)
            method, attribute, values = query["method"], query.get("attribute"), query.get("values", [])
            if method == "equal":
                wanted = set(values)
                rows = [
                    (rid, d) for rid, d in rows
                    if (rid if attribute == "$id" else d.get(attribute)) in wanted
                ]
            elif method in ("orderAsc", "orderDesc"):
                orders.append((attribute, method == "orderDesc"))
            elif method == "limit":
                limits_seen += 1
                if limits_seen > 1:  # the real API does not accept repeated limits
                    raise AppwriteException("duplicate limit", 400, "general_query_invalid")
                limit = values[0]
            elif method == "cursorAfter":
                cursor = values[0]
            else:
                raise AssertionError(f"unsupported query {method}")
        for attribute, descending in reversed(orders):
            rows.sort(key=lambda item: str(item[1].get(attribute)), reverse=descending)
        total = len(rows)
        if cursor is not None:
            ids = [rid for rid, _ in rows]
            rows = rows[ids.index(cursor) + 1:]
        rows = rows[:limit]
        return SimpleNamespace(total=total, rows=[self._row(rid, data) for rid, data in rows])

    @staticmethod
    def _row(row_id, data):
        return SimpleNamespace(id=row_id, data=dict(data))
