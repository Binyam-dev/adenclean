"""The one-off script that copies an old SQLite file into Appwrite."""

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_sqlite_to_appwrite as migration  # noqa: E402
import store as storage  # noqa: E402

try:
    from fake_appwrite import FakeTablesDB  # noqa: F401
    HAVE_APPWRITE = True
except ImportError:
    HAVE_APPWRITE = False

NOW = "2026-01-05T10:00:00+00:00"


def old_file(directory):
    """A file shaped like the earliest version: no status columns, no private link."""
    path = Path(directory) / "legacy.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript("""
            CREATE TABLE customer_requests (id TEXT PRIMARY KEY, created_at TEXT, full_name TEXT, email TEXT,
                area TEXT, service_type TEXT, preferred_date TEXT, preferred_time TEXT, notes TEXT, consent INTEGER);
            CREATE TABLE customer_reviews (id TEXT PRIMARY KEY, request_id TEXT, created_at TEXT, rating INTEGER,
                message TEXT, consent INTEGER, status TEXT, status_updated_at TEXT);
            CREATE TABLE status_history (id INTEGER PRIMARY KEY AUTOINCREMENT, record_type TEXT, record_id TEXT,
                old_status TEXT, new_status TEXT, note TEXT, actor TEXT, created_at TEXT);
        """)
        connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?,?,?,?,?)",
                           ("REQ000000001", NOW, "Pat Example", "pat@example.com", "Silver Spring", "deep",
                            "2026-02-01", "morning", None, 1))
        connection.execute("INSERT INTO customer_reviews VALUES (?,?,?,?,?,?,?,?)",
                           ("REV000000001", "REQ000000001", NOW, 5, "Lovely and thorough work.", 1, "new", NOW))
        connection.execute("INSERT INTO status_history (record_type, record_id, old_status, new_status, note, actor, created_at) "
                           "VALUES ('requests', 'REQ000000001', NULL, 'pending', NULL, 'system', ?)", (NOW,))
    return path


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = old_file(self.directory.name)
        self.target = storage.open_store({"ADENCLEAN_STORAGE": "memory"})
        self.lines = []

    def test_copies_old_rows_and_fills_what_appwrite_requires(self):
        results = migration.migrate(self.path, self.target, out=self.lines.append)
        self.assertEqual(results["customer_requests"], (1, 0))
        self.assertEqual(results["customer_reviews"], (1, 0))
        self.assertEqual(results["status_history"], (1, 0))
        self.assertEqual(results["admins"], (0, 0))  # table absent from the old file
        self.assertEqual(self.target.get_status("requests", "REQ000000001"), "pending")
        records, counts, histories = self.target.list_records("requests", "all", ["pending"])
        self.assertEqual((records[0]["full_name"], records[0]["notes"], counts["pending"]), ("Pat Example", "", 1))
        self.assertEqual(len(histories["REQ000000001"]), 1)
        self.assertEqual(self.target.get_review_for_request("REQ000000001")["rating"], 5)

    def test_second_run_skips_rows_and_never_overwrites(self):
        migration.migrate(self.path, self.target, out=self.lines.append)
        self.target.set_status("requests", "REQ000000001", "pending", "approved", NOW,
                               {"record_type": "requests", "record_id": "REQ000000001", "old_status": "pending",
                                "new_status": "approved", "note": "", "actor": "a@example.com", "created_at": NOW})
        results = migration.migrate(self.path, self.target, out=self.lines.append)
        self.assertEqual(results["customer_requests"], (0, 1))
        self.assertEqual(self.target.get_status("requests", "REQ000000001"), "approved")

    def test_dry_run_writes_nothing_and_output_has_no_customer_details(self):
        results = migration.migrate(self.path, None, dry_run=True, out=self.lines.append)
        self.assertEqual(results["customer_requests"], (1, 0))
        self.assertEqual(self.target.export_all()["customer_requests"], [])
        printed = " ".join(self.lines)
        for private in ("Pat", "pat@example.com", "Silver Spring", "Lovely"):
            self.assertNotIn(private, printed)

    def test_bad_usage_returns_an_error_code(self):
        self.assertEqual(migration.main([], out=self.lines.append), 2)
        self.assertEqual(migration.main(["missing.sqlite3"], out=self.lines.append), 2)


if __name__ == "__main__":
    unittest.main()
