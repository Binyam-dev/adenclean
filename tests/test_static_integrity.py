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
        for filename in (".gitignore", ".replitignore"):
            ignored = (ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(file=filename):
                self.assertIn("/data/", ignored)
                self.assertIn("__pycache__/", ignored)
                self.assertIn("*.py[cod]", ignored)
                self.assertIn(".env", ignored)


if __name__ == "__main__":
    unittest.main()
