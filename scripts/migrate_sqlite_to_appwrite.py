"""Copy records from an old AdenClean SQLite file into Appwrite.

The server stopped using SQLite when production moved to Appwrite. This is the only code
that still reads one, for anyone holding a file from before the move.

    python scripts/migrate_sqlite_to_appwrite.py old.sqlite3 --dry-run   # count only
    python scripts/migrate_sqlite_to_appwrite.py old.sqlite3             # copy

It needs the same APPWRITE_* settings as the server. It is safe to run twice: a row whose
id already exists in Appwrite is skipped, never overwritten. It prints counts only, never
customer details. Status history rows have no stable id in the old file, so run the copy
once per file to avoid duplicate history lines.
"""

import hashlib
import secrets
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store as storage  # noqa: E402

TABLES = ("customer_requests", "cleaner_availability", "customer_reviews", "service_issues",
          "admins", "status_history")


def _columns(table):
    return [column[0] for column in storage.APPWRITE_SCHEMA[table]["columns"]]


def _prepare(table, row):
    """Shape one old row for Appwrite. Returns (row_id, data)."""
    data = {key: row[key] for key in _columns(table) if key in row.keys()}
    if table == "customer_requests":
        data["notes"] = data.get("notes") or ""
        data["status"] = data.get("status") or "pending"
        data["status_updated_at"] = data.get("status_updated_at") or data["created_at"]
        if not data.get("feedback_token_hash"):
            # Very old requests had no private link. Appwrite needs a unique value, so store
            # the hash of a random token nobody holds: the request can never be opened by link.
            data["feedback_token_hash"] = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    if table == "cleaner_availability":
        data["status"] = data.get("status") or "pending"
        data["status_updated_at"] = data.get("status_updated_at") or data["created_at"]
    if table == "status_history":
        data["note"] = data.get("note") or ""
        return uuid.uuid4().hex, data
    return str(row["id"]), data


def migrate(sqlite_path, target, dry_run=False, out=print):
    """Copy every table. Returns {table: (copied, skipped)}."""
    results = {}
    with closing(sqlite3.connect(f"file:{Path(sqlite_path).as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        present = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in TABLES:
            if table not in present:
                results[table] = (0, 0)
                continue
            copied = skipped = 0
            for row in connection.execute(f"SELECT * FROM {table}"):
                row_id, data = _prepare(table, row)
                if dry_run:
                    copied += 1
                    continue
                try:
                    target._create(table, row_id, data)
                    copied += 1
                except storage.Conflict:
                    skipped += 1
            results[table] = (copied, skipped)
            verb = "would copy" if dry_run else "copied"
            out(f"{table}: {verb} {copied}, skipped {skipped} already in Appwrite")
    return results


def main(argv, out=print):
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 1 or not Path(paths[0]).is_file():
        out("Usage: python scripts/migrate_sqlite_to_appwrite.py path/to/old.sqlite3 [--dry-run]")
        return 2
    dry_run = "--dry-run" in argv
    target = None if dry_run else storage.open_store()
    if target is not None and target.name != "appwrite":
        out("Set ADENCLEAN_STORAGE=appwrite and the APPWRITE_* settings first.")
        return 2
    migrate(paths[0], target, dry_run=dry_run, out=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
