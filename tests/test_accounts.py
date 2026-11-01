import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402
import create_admin  # noqa: E402
import store as storage  # noqa: E402


class PasswordTests(unittest.TestCase):
    def test_hash_verifies_and_is_salted(self):
        first, second = auth.hash_password("a long enough pass"), auth.hash_password("a long enough pass")
        self.assertNotEqual(first, second)
        self.assertNotIn("a long enough pass", first)
        self.assertTrue(auth.verify_password("a long enough pass", first))
        self.assertFalse(auth.verify_password("a long enough pasS", first))

    def test_malformed_hashes_never_verify_or_raise(self):
        for stored in ("", "plain", "scrypt$1$2", "bcrypt$a$b$c$d$e", "scrypt$x$8$1$AA==$AA=="):
            self.assertFalse(auth.verify_password("anything", stored))

    def test_length_rules(self):
        self.assertTrue(auth.password_problem("short"))
        self.assertTrue(auth.password_problem("x" * 300))
        self.assertEqual(auth.password_problem("twelve chars!"), "")


class CreateAdminTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = storage.SqliteStore(Path(directory.name) / "a.sqlite3")
        self.output = []

    def run_cli(self, *argv, passwords=("a good long password",) * 2):
        queue = list(passwords)
        return create_admin.main(list(argv), self.store, lambda _prompt: queue.pop(0), self.output.append)

    def test_add_list_disable_enable(self):
        self.assertEqual(self.run_cli("add", "Boss@Example.com"), 0)
        admin = self.store.get_admin_by_email("boss@example.com")
        self.assertTrue(auth.verify_password("a good long password", admin["password_hash"]))
        self.assertEqual(self.run_cli("add", "boss@example.com"), 1)  # duplicate
        self.assertEqual(self.run_cli("disable", "boss@example.com"), 0)
        self.assertFalse(self.store.has_admins())
        self.assertEqual(self.run_cli("enable", "boss@example.com"), 0)
        self.assertTrue(self.store.has_admins())
        self.assertEqual(self.run_cli("list"), 0)
        self.assertIn("boss@example.com", self.output[-1])
        self.assertNotIn("password", self.output[-1].lower())

    def test_rejects_weak_mismatched_and_invalid_input(self):
        self.assertEqual(self.run_cli("add", "a@example.com", passwords=("short", "short")), 2)
        self.assertEqual(self.run_cli("add", "a@example.com", passwords=("a good long password", "different long one")), 2)
        self.assertEqual(self.run_cli("add", "not-an-email"), 2)
        self.assertEqual(self.run_cli("disable", "ghost@example.com"), 1)
        self.assertEqual(self.run_cli(), 2)
        self.assertFalse(self.store.has_admins())


if __name__ == "__main__":
    unittest.main()
