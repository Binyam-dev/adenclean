"""Upgrade real legacy SQLite files without losing submissions or later updates."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import store as storage
from test_store import NOW, STATUSES, history, request_row


class SqliteMigrationTests(unittest.TestCase):
    def make_legacy_database(self, directory, existing_columns):
        path = Path(directory) / 'legacy.sqlite3'
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript('''
                CREATE TABLE customer_requests (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    full_name TEXT NOT NULL, email TEXT NOT NULL, area TEXT NOT NULL,
                    service_type TEXT NOT NULL, preferred_date TEXT NOT NULL,
                    preferred_time TEXT NOT NULL, notes TEXT NOT NULL, consent INTEGER NOT NULL
                );
                CREATE TABLE cleaner_availability (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    full_name TEXT NOT NULL, email TEXT NOT NULL, area TEXT NOT NULL,
                    service_types TEXT NOT NULL, available_date TEXT NOT NULL,
                    start_time TEXT NOT NULL, end_time TEXT NOT NULL, consent INTEGER NOT NULL
                );
            ''')
            for table in ('customer_requests', 'cleaner_availability'):
                for column in existing_columns:
                    default = "'pending'" if column == 'status' else "''"
                    connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}')
                connection.execute(
                    f'INSERT INTO {table} VALUES ({",".join("?" for _ in range(10 + len(existing_columns)))})',
                    ('legacy', NOW, 'Original Person', 'old@example.com', 'Silver Spring',
                     'routine', '2026-12-01', '09:00', '11:00', 1,
                     *('approved' if c == 'status' else '' for c in existing_columns)),
                )
        return path

    def test_legacy_submissions_survive_upgrade_and_repeated_startup(self):
        # Cover pre-status files and partially upgraded files independently.
        for existing_columns in ((), ('status',), ('status_updated_at',), ('status', 'status_updated_at')):
            with self.subTest(columns=existing_columns), tempfile.TemporaryDirectory() as directory:
                path = self.make_legacy_database(directory, existing_columns)
                opened = storage.SqliteStore(path)
                initial_status = 'approved' if 'status' in existing_columns else 'pending'
                for kind in ('requests', 'availability'):
                    records, counts, trails = opened.list_records(kind, 'all', STATUSES)
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]['full_name'], 'Original Person')
                    self.assertEqual(records[0]['email'], 'old@example.com')
                    self.assertEqual(records[0]['created_at'], NOW)
                    self.assertEqual(records[0]['status'], initial_status)
                    self.assertEqual(records[0]['status_updated_at'], NOW)
                    self.assertEqual(counts[initial_status], 1)
                    self.assertEqual(trails['legacy'], [])
                    opened.set_status(kind, 'legacy', initial_status, 'completed', '2026-11-02T01:00:00+00:00',
                                      history(kind, 'legacy', 'completed', initial_status))
                with closing(sqlite3.connect(path)) as connection:
                    self.assertIsNone(connection.execute('SELECT feedback_token_hash FROM customer_requests').fetchone()[0])
                opened.add_request(request_row(), history('requests', 'REQ000000001'))
                before = opened.export_all()
                opened.init()
                reopened = storage.SqliteStore(path)
                self.assertEqual(reopened.export_all(), before)
                self.assertEqual(reopened.find_request_by_token_hash('h1')['id'], 'REQ000000001')
                with self.assertRaises(storage.Conflict):
                    reopened.add_request(request_row('REQ000000002'), history('requests', 'REQ000000002'))

    def test_current_database_preserves_feedback_tokens_and_nonempty_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'current.sqlite3'
            opened = storage.SqliteStore(path)
            opened.add_request(request_row(status='completed'), history('requests', 'REQ000000001', 'completed'))
            before = opened.export_all()
            reopened = storage.SqliteStore(path)
            self.assertEqual(reopened.export_all(), before)
            self.assertEqual(reopened.find_request_by_token_hash('h1')['status_updated_at'], NOW)


if __name__ == '__main__':
    unittest.main()
