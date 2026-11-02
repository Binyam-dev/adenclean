"""The same behaviour checks run against both storage backends."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store as storage  # noqa: E402

try:
    from fake_appwrite import FakeTablesDB
    HAVE_APPWRITE = True
except ImportError:  # the appwrite package is not installed
    HAVE_APPWRITE = False

NOW = "2026-11-01T12:00:00+00:00"
STATUSES = ["pending", "approved", "declined", "completed", "cancelled"]


def request_row(reference="REQ000000001", token_hash="h1", status="pending", created=NOW):
    return {
        "id": reference, "created_at": created, "full_name": "Test Person",
        "email": "t@example.com", "area": "Silver Spring", "service_type": "routine",
        "preferred_date": "2026-12-01", "preferred_time": "morning", "notes": "",
        "consent": 1, "status": status, "status_updated_at": created,
        "feedback_token_hash": token_hash,
    }


def history(record_type, record_id, new="pending", old=None, actor="system", created=NOW):
    return {
        "record_type": record_type, "record_id": record_id, "old_status": old,
        "new_status": new, "note": "n", "actor": actor, "created_at": created,
    }


def review_row(request_id, reference="REV000000001"):
    return {
        "id": reference, "request_id": request_id, "created_at": NOW, "rating": 5,
        "message": "Lovely job done", "consent": 1, "status": "new",
        "status_updated_at": NOW,
    }


class StoreContract:
    """Mixin: subclasses provide make_store()."""

    def setUp(self):
        self.store = self.make_store()

    def test_request_roundtrip_and_token_lookup(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        found = self.store.find_request_by_token_hash("h1")
        self.assertEqual(found["id"], "REQ000000001")
        self.assertEqual(found["status"], "pending")
        self.assertIsNone(self.store.find_request_by_token_hash("nope"))

    def test_duplicate_feedback_token_is_rejected(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        with self.assertRaises(storage.Conflict):
            self.store.add_request(
                request_row("REQ000000002", token_hash="h1"), history("requests", "REQ000000002")
            )

    def test_one_review_and_one_issue_per_request(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        self.store.add_review(review_row("REQ000000001"), history("reviews", "REV000000001", "new"))
        with self.assertRaises(storage.Conflict):
            self.store.add_review(
                review_row("REQ000000001", "REV000000002"), history("reviews", "REV000000002", "new")
            )
        self.assertIsNotNone(self.store.get_review_for_request("REQ000000001"))
        self.assertIsNone(self.store.get_issue_for_request("REQ000000001"))

    def test_status_change_checks_expected_status_and_records_history(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        self.store.set_status(
            "requests", "REQ000000001", "pending", "approved", NOW,
            history("requests", "REQ000000001", "approved", "pending", "a@b.co"),
        )
        self.assertEqual(self.store.get_status("requests", "REQ000000001"), "approved")
        with self.assertRaises(storage.Conflict):  # stale expected status
            self.store.set_status(
                "requests", "REQ000000001", "pending", "declined", NOW,
                history("requests", "REQ000000001", "declined", "pending", "a@b.co"),
            )
        with self.assertRaises(storage.NotFound):
            self.store.get_status("requests", "MISSING")

        records, counts, histories = self.store.list_records("requests", "all", STATUSES)
        self.assertEqual(counts["approved"], 1)
        self.assertEqual(counts["pending"], 0)
        trail = histories["REQ000000001"]
        self.assertEqual([h["new_status"] for h in trail], ["pending", "approved"])
        self.assertEqual(trail[-1]["actor"], "a@b.co")

    def test_list_filters_orders_and_hides_private_fields(self):
        for number, (status, created) in enumerate(
            [("pending", "2026-11-01T01:00:00+00:00"), ("approved", "2026-11-01T02:00:00+00:00"),
             ("pending", "2026-11-01T03:00:00+00:00")]
        ):
            reference = f"REQ00000000{number}"
            self.store.add_request(
                request_row(reference, f"hash{number}", status, created),
                history("requests", reference, status, created=created),
            )
        records, counts, _ = self.store.list_records("requests", "all", STATUSES)
        self.assertEqual([r["id"] for r in records], ["REQ000000002", "REQ000000001", "REQ000000000"])
        self.assertNotIn("feedback_token_hash", records[0])
        self.assertNotIn("consent", records[0])
        self.assertEqual(counts["pending"], 2)
        pending, _, _ = self.store.list_records("requests", "pending", STATUSES)
        self.assertEqual({r["id"] for r in pending}, {"REQ000000002", "REQ000000000"})

    def test_reviews_list_includes_request_details(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        self.store.add_review(review_row("REQ000000001"), history("reviews", "REV000000001", "new"))
        records, counts, histories = self.store.list_records("reviews", "all", ["new", "reviewed"])
        self.assertEqual(records[0]["full_name"], "Test Person")
        self.assertEqual(records[0]["service_type"], "routine")
        self.assertEqual(counts["new"], 1)
        self.assertEqual(len(histories["REV000000001"]), 1)

    def test_availability_roundtrip(self):
        row = {
            "id": "AVL000000001", "created_at": NOW, "full_name": "Cleaner", "email": "c@example.com",
            "area": "Takoma Park", "service_types": '["routine"]', "available_date": "2026-12-02",
            "start_time": "09:00", "end_time": "12:00", "consent": 1, "status": "pending",
            "status_updated_at": NOW,
        }
        self.store.add_availability(row, history("availability", "AVL000000001"))
        records, counts, _ = self.store.list_records("availability", "all", ["pending", "approved", "declined"])
        self.assertEqual(records[0]["service_types"], '["routine"]')
        self.assertEqual(counts["pending"], 1)

    def test_more_than_one_page_of_history_is_returned(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        for number in range(130):
            self.store.set_status(
                "requests", "REQ000000001",
                "pending" if number % 2 == 0 else "approved",
                "approved" if number % 2 == 0 else "pending",
                f"2026-11-02T00:{number // 60:02d}:{number % 60:02d}+00:00",
                history("requests", "REQ000000001", "x", "y",
                        created=f"2026-11-02T00:{number // 60:02d}:{number % 60:02d}+00:00"),
            )
        _, _, histories = self.store.list_records("requests", "all", STATUSES)
        self.assertEqual(len(histories["REQ000000001"]), 131)

    def test_admin_accounts(self):
        self.assertFalse(self.store.has_admins())
        row = {"id": "a" * 32, "email": "a@example.com", "password_hash": "x", "role": "admin",
               "active": 1, "created_at": NOW}
        self.store.add_admin(row)
        self.assertTrue(self.store.has_admins())
        self.assertEqual(self.store.get_admin_by_email("a@example.com")["id"], "a" * 32)
        self.assertEqual(self.store.get_admin("a" * 32)["email"], "a@example.com")
        self.assertIsNone(self.store.get_admin("b" * 32))
        with self.assertRaises(storage.Conflict):
            self.store.add_admin({**row, "id": "b" * 32})
        self.store.set_admin_active("a@example.com", False)
        self.assertFalse(self.store.has_admins())
        self.assertNotIn("password_hash", self.store.list_admins()[0])

    def test_export_has_no_admin_hashes(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        self.store.add_admin({"id": "a" * 32, "email": "a@example.com", "password_hash": "secret",
                              "role": "admin", "active": 1, "created_at": NOW})
        exported = self.store.export_all()
        self.assertNotIn("admins", exported)
        self.assertEqual(len(exported["customer_requests"]), 1)
        self.assertNotIn("secret", str(exported))


class SqliteStoreTests(StoreContract, unittest.TestCase):
    def make_store(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        return storage.SqliteStore(Path(self.directory.name) / "t.sqlite3")


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class AppwriteStoreTests(StoreContract, unittest.TestCase):
    def make_store(self):
        self.fake = FakeTablesDB()
        return storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean",
                                     tables_db=self.fake)

    def test_rows_are_created_with_no_client_permissions(self):
        self.store.add_request(request_row(), history("requests", "REQ000000001"))
        creates = [call for call in self.fake.calls if call[0] == "create_row"]
        self.assertTrue(creates)
        self.assertTrue(all(call[2] == [] for call in creates))

    def test_unexpected_failures_become_store_errors_without_details(self):
        def boom(**_):
            raise RuntimeError("secret connection string")
        self.fake.list_rows = boom
        with self.assertRaises(storage.StoreError) as raised:
            self.store.find_request_by_token_hash("x")
        self.assertNotIn("secret", str(raised.exception))


class OpenStoreTests(unittest.TestCase):
    def test_defaults_to_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            opened = storage.open_store({}, sqlite_path=Path(directory) / "x.sqlite3")
            self.assertEqual(opened.name, "sqlite")

    def test_appwrite_mode_refuses_to_start_without_settings(self):
        with self.assertRaises(RuntimeError) as raised:
            storage.open_store({"ADENCLEAN_STORAGE": "appwrite"})
        self.assertIn("APPWRITE_API_KEY", str(raised.exception))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(RuntimeError):
            storage.open_store({"ADENCLEAN_STORAGE": "oops"})


if __name__ == "__main__":
    unittest.main()
