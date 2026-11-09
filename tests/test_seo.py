"""Search-engine basics: crawl files, canonical links, one URL per page, sensible caching."""

import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402

STATIC = ROOT / "static"
SITE = "https://adenclean.onrender.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class SeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), main.AdenCleanHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = urllib.request.build_opener(NoRedirect)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path, method="GET"):
        # Large bodies are fetched with HEAD (headers only) on purpose: on the Windows dev
        # machine, downloading 25-45 KB files over loopback sometimes stalls ~20 s and is
        # reset (antivirus inspection; the server has already logged a 200). Headers are all
        # these tests need for big files.
        request = urllib.request.Request(self.base + path, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def test_robots_and_sitemap_are_served_and_agree(self):
        status, headers, body = self.get("/robots.txt")
        self.assertEqual(status, 200)
        robots = body.decode()
        self.assertIn(f"Sitemap: {SITE}/sitemap.xml", robots)
        self.assertIn("Disallow: /api/", robots)
        status, headers, body = self.get("/sitemap.xml")
        self.assertEqual(status, 200)
        self.assertIn("xml", headers["Content-Type"])
        urls = [e.text for e in ElementTree.fromstring(body).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertEqual(urls, [f"{SITE}/", f"{SITE}/policies.html"])

    def test_noindex_pages_are_not_in_the_sitemap_and_not_blocked_from_crawling(self):
        sitemap = (STATIC / "sitemap.xml").read_text(encoding="utf-8")
        robots = (STATIC / "robots.txt").read_text(encoding="utf-8")
        for page in ("admin.html", "feedback.html"):
            self.assertIn("noindex", (STATIC / page).read_text(encoding="utf-8"))
            self.assertNotIn(page, sitemap)
            self.assertNotIn(page, robots)  # blocking would hide the noindex tag from crawlers

    def test_canonical_links_match_the_sitemap_and_site_address(self):
        for page, url in (("index.html", f"{SITE}/"), ("policies.html", f"{SITE}/policies.html")):
            html = (STATIC / page).read_text(encoding="utf-8")
            self.assertEqual(re.findall(r'<link rel="canonical" href="([^"]+)"', html), [url], page)
        home = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'<meta property="og:url" content="{SITE}/">', home)

    def test_home_page_names_the_service_and_place(self):
        home = (STATIC / "index.html").read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", home).group(1)
        self.assertIn("Silver Spring", title)
        self.assertIn("cleaning", title.lower())
        description = re.search(r'<meta name="description" content="([^"]+)"', home).group(1)
        self.assertLessEqual(len(description), 170)
        self.assertIn("Silver Spring", description)

    def test_structured_data_is_valid_json_and_matches_the_page(self):
        home = (STATIC / "index.html").read_text(encoding="utf-8")
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', home, flags=re.S)
        self.assertEqual(len(blocks), 1)
        graph = json.loads(blocks[0])["@graph"]
        self.assertEqual({item["@type"] for item in graph}, {"Organization", "WebSite"})
        for item in graph:
            self.assertTrue(item["url"].startswith(SITE))
        organization = next(i for i in graph if i["@type"] == "Organization")
        for fact in (organization["email"], organization["telephone"].replace("+1", "")):
            self.assertIn(fact, home.replace("tel:+1", "").replace("(240) 342-6088", "2403426088"))

    def test_share_image_exists(self):
        self.assertTrue((STATIC / "og-image.png").is_file())
        status, headers, body = self.get("/og-image.png", "HEAD")
        self.assertEqual((status, headers["Content-Type"]), (200, "image/png"))

    def test_index_html_redirects_to_the_root(self):
        status, headers, _ = self.get("/index.html")
        self.assertEqual((status, headers["Location"]), (301, "/"))
        self.assertEqual(self.get("/", "HEAD")[0], 200)

    def test_cache_policy(self):
        self.assertEqual(main.cache_policy("/api/service-requests"), "no-store")
        self.assertEqual(main.cache_policy("/api/v1/me?x=1"), "no-store")
        self.assertEqual(main.cache_policy("/"), "no-cache")
        self.assertEqual(main.cache_policy("/styles.css"), "no-cache")
        self.assertEqual(main.cache_policy("/app.js"), "no-cache")
        self.assertEqual(main.cache_policy("/og-image.png"), "public, max-age=86400")
        self.assertEqual(main.cache_policy("/favicon.svg"), "public, max-age=86400")
        self.assertEqual(self.get("/", "HEAD")[1]["Cache-Control"], "no-cache")
        self.assertEqual(self.get("/api/admin/session")[1]["Cache-Control"], "no-store")

    def test_pages_can_be_revalidated_with_a_304(self):
        status, headers, _ = self.get("/robots.txt")
        request = urllib.request.Request(self.base + "/robots.txt", headers={"If-Modified-Since": headers["Last-Modified"]})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.opener.open(request, timeout=30)
        self.assertEqual(caught.exception.code, 304)


if __name__ == "__main__":
    unittest.main()
