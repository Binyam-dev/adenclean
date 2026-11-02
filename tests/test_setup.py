import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store as storage  # noqa: E402

try:
    from fake_appwrite import FakeTablesDB
    import setup_appwrite
    HAVE_APPWRITE = True
except ImportError:
    HAVE_APPWRITE = False


@unittest.skipUnless(HAVE_APPWRITE, "appwrite package not installed")
class ProvisionTests(unittest.TestCase):
    def test_creates_everything_in_the_schema_and_is_safe_to_rerun(self):
        fake = FakeTablesDB(provisioned=False)
        setup_appwrite.provision(fake, "adenclean", out=lambda _line: None)

        self.assertIn("adenclean", fake.databases)
        self.assertEqual(set(fake.tables), set(storage.APPWRITE_SCHEMA))
        for table_id, spec in storage.APPWRITE_SCHEMA.items():
            self.assertEqual(set(fake.tables[table_id]["columns"]), {c[0] for c in spec["columns"]})
            self.assertEqual(set(fake.tables[table_id]["indexes"]), {i[0] for i in spec["indexes"]})
            # no client access: empty permissions and no per-row security
            self.assertEqual(fake.table_permissions[table_id], ([], False))

        calls_after_first_run = len(fake.calls)
        setup_appwrite.provision(fake, "adenclean", out=lambda _line: None)
        self.assertEqual(len(fake.calls), calls_after_first_run, "a second run must create nothing")

    def test_provisioned_database_supports_the_store(self):
        fake = FakeTablesDB(provisioned=False)
        setup_appwrite.provision(fake, "adenclean", out=lambda _line: None)
        store = storage.AppwriteStore("https://example.invalid/v1", "p", "k", "adenclean", tables_db=fake)
        self.assertFalse(store.has_admins())

    def test_rejected_key_gives_a_clear_message_without_a_traceback(self):
        messages = []
        code = setup_appwrite.explain_failure(
            type("E", (Exception,), {"code": 401, "message": "key not valid"})("x"), messages.append
        )
        self.assertEqual(code, 1)
        self.assertIn("adenclean-setup", messages[0])
        self.assertNotIn("standard_", messages[0])


if __name__ == "__main__":
    unittest.main()
