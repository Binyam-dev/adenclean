import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    "/": ROOT / "static" / "index.html",
    "/admin.html": ROOT / "static" / "admin.html",
    "/feedback.html": ROOT / "static" / "feedback.html",
    "/policies.html": ROOT / "static" / "policies.html",
}


class PageReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])


class StaticIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {}
        for route, path in PAGES.items():
            parser = PageReferences()
            parser.feed(path.read_text(encoding="utf-8"))
            cls.pages[route] = parser

    def test_internal_page_links_and_anchors_exist(self):
        for route, page in self.pages.items():
            for href in page.links:
                target = urlsplit(href)
                if target.scheme or target.netloc:
                    continue

                target_route = target.path or route
                if target_route.endswith("/"):
                    target_route = target_route.rstrip("/") or "/"

                with self.subTest(source=route, href=href):
                    self.assertIn(target_route, self.pages)
                    if target.fragment:
                        self.assertIn(target.fragment, self.pages[target_route].ids)

    def test_customer_contact_links_are_present(self):
        home = PAGES["/"].read_text(encoding="utf-8")
        self.assertIn("Silver Spring, Maryland", home)
        self.assertIn('href="mailto:applications@adeneats.com"', home)
        self.assertIn('href="tel:+12403426088"', home)

    def test_local_data_and_environment_files_are_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        # /data/ held the old local database (customer details, admin password hashes); a checkout
        # that ran it still has the file, so it must stay ignored after the Appwrite move.
        for pattern in ("__pycache__/", "*.py[cod]", ".env", "/backups/", "/data/", "*.sqlite3"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, ignored)

    def test_no_replit_supabase_or_sqlite_leftovers(self):
        # The data layer is Appwrite only. scripts/migrate_sqlite_to_appwrite.py is the one
        # allowed place that reads an old SQLite file, and this test names the words it bans.
        allowed = {"scripts/migrate_sqlite_to_appwrite.py", "tests/test_static_integrity.py",
                   "tests/test_migrate.py", "tests/test_store.py", "tests/test_app.py",
                   "README.md",  # the README only points at the migration script
                   ".gitignore"}  # keeps old local database files out of Git
        # Only files tracked by git count: a local virtualenv, node_modules or log file is not ours.
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        for relative in tracked:
            path = ROOT / relative
            if not path.is_file() or relative.startswith("docs/"):
                continue
            if relative in allowed or path.suffix in {".png", ".ttf", ".ico", ".jpg"}:
                continue
            if path.name == "package-lock.json":
                continue
            with self.subTest(file=relative):
                self.assertNotIn("replit", path.name.lower())
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                for word in ("sqlite", "supabase", "replit"):
                    self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
