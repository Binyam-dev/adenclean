"""Create the AdenClean database, tables, columns and indexes in Appwrite.

Run once after setting APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID and APPWRITE_API_KEY
(the key needs the databases.*, tables.*, columns.*, indexes.* and rows.* scopes):

    python setup_appwrite.py

Safe to run again: anything that already exists is skipped. Tables are created with
no client permissions, so only the server API key can read or write customer data.
"""

import os
import sys
import time

import store as storage


def exists(call):
    try:
        call()
        return True
    except Exception as error:
        if getattr(error, "code", 0) == 404:
            return False
        raise


def wait_for_columns(tables_db, database_id, table_id, keys, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        columns = tables_db.list_columns(database_id=database_id, table_id=table_id).columns
        # The SDK returns an Enum (ColumnStatus), not a plain string.
        ready = {c.key: str(getattr(c.status, "value", c.status)) for c in columns}
        broken = [key for key in keys if ready.get(key) in {"failed", "stuck"}]
        if broken:
            raise RuntimeError(f"Appwrite could not create {table_id} columns: {', '.join(broken)}")
        if all(ready.get(key) == "available" for key in keys):
            return
        time.sleep(1.5)
    raise RuntimeError(f"Columns for {table_id} were not ready after {timeout}s.")


def provision(tables_db, database_id, out=print):
    from appwrite.enums.tables_db_index_type import TablesDBIndexType

    if not exists(lambda: tables_db.get(database_id=database_id)):
        tables_db.create(database_id=database_id, name="AdenClean")
        out(f"created database {database_id}")

    index_types = {
        "key": TablesDBIndexType.KEY,
        "unique": TablesDBIndexType.UNIQUE,
    }
    for table_id, spec in storage.APPWRITE_SCHEMA.items():
        if not exists(lambda: tables_db.get_table(database_id=database_id, table_id=table_id)):
            tables_db.create_table(
                database_id=database_id,
                table_id=table_id,
                name=table_id,
                permissions=[],
                row_security=False,
            )
            out(f"created table {table_id}")

        existing = {
            c.key
            for c in tables_db.list_columns(database_id=database_id, table_id=table_id).columns
        }
        for key, kind, size, required in spec["columns"]:
            if key in existing:
                continue
            common = dict(database_id=database_id, table_id=table_id, key=key, required=required)
            if kind == storage.VARCHAR:
                tables_db.create_varchar_column(size=size, **common)
            elif kind == storage.TEXT:
                tables_db.create_text_column(**common)
            else:
                tables_db.create_integer_column(**common)
            out(f"  column {table_id}.{key}")
        wait_for_columns(tables_db, database_id, table_id, [c[0] for c in spec["columns"]])

        existing_indexes = {
            i.key
            for i in tables_db.list_indexes(database_id=database_id, table_id=table_id).indexes
        }
        for key, kind, columns in spec["indexes"]:
            if key in existing_indexes:
                continue
            tables_db.create_index(
                database_id=database_id,
                table_id=table_id,
                key=key,
                type=index_types[kind],
                columns=columns,
            )
            out(f"  index {table_id}.{key}")


def main():
    missing = [
        name
        for name in ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_API_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        print("Missing settings: " + ", ".join(missing))
        return 2

    from appwrite.client import Client
    from appwrite.services.tables_db import TablesDB

    client = (
        Client()
        .set_endpoint(os.environ["APPWRITE_ENDPOINT"])
        .set_project(os.environ["APPWRITE_PROJECT_ID"])
        .set_key(os.environ["APPWRITE_API_KEY"])
    )
    provision(TablesDB(client), os.environ.get("APPWRITE_DATABASE_ID", "adenclean"))
    print("Done. Next: python create_admin.py add you@example.com")
    return 0


if __name__ == "__main__":
    sys.exit(main())
