"""A small in-memory stand-in for Appwrite's TablesDB, used only by the tests.

It understands the handful of Query methods AdenClean uses (equal, orderAsc/Desc,
limit, cursorAfter) and enforces the unique indexes declared in APPWRITE_SCHEMA, so
the Appwrite store's logic can be exercised without a network or an account.
"""

import json
from types import SimpleNamespace

from appwrite.exception import AppwriteException

import store as storage


class FakeTablesDB:
    def __init__(self):
        self.tables = {name: {} for name in storage.APPWRITE_SCHEMA}
        self.calls = []

    def _table(self, table_id):
        if table_id not in self.tables:
            raise AppwriteException("table not found", 404, "table_not_found")
        return self.tables[table_id]

    def create_row(self, database_id, table_id, row_id, data, permissions=None, **_):
        self.calls.append(("create_row", table_id, permissions))
        table = self._table(table_id)
        if row_id in table:
            raise AppwriteException("exists", 409, "row_already_exists")
        for key, kind, columns in (
            (i[0], i[1], i[2]) for i in storage.APPWRITE_SCHEMA[table_id]["indexes"]
        ):
            if kind != "unique":
                continue
            value = tuple(data.get(c) for c in columns)
            if any(tuple(r.get(c) for c in columns) == value for r in table.values()):
                raise AppwriteException("duplicate", 409, "row_already_exists")
        for column, _kind, _size, required in storage.APPWRITE_SCHEMA[table_id]["columns"]:
            if required and data.get(column) is None:
                raise AppwriteException(f"missing {column}", 400, "document_invalid_structure")
        table[row_id] = dict(data)
        return self._row(row_id, table[row_id])

    def get_row(self, database_id, table_id, row_id, **_):
        table = self._table(table_id)
        if row_id not in table:
            raise AppwriteException("not found", 404, "row_not_found")
        return self._row(row_id, table[row_id])

    def update_row(self, database_id, table_id, row_id, data=None, **_):
        table = self._table(table_id)
        if row_id not in table:
            raise AppwriteException("not found", 404, "row_not_found")
        table[row_id].update(data or {})
        return self._row(row_id, table[row_id])

    def list_rows(self, database_id, table_id, queries=None, **_):
        rows = [(row_id, dict(data)) for row_id, data in self._table(table_id).items()]
        limit, cursor, orders = 25, None, []
        for raw in queries or []:
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
        return SimpleNamespace(
            total=total, rows=[self._row(rid, data) for rid, data in rows]
        )

    @staticmethod
    def _row(row_id, data):
        return SimpleNamespace(id=row_id, data=dict(data))
