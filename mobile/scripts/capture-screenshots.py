"""Builds the store screenshots from the real app.

    python scripts/capture-screenshots.py

It exports the app for web, runs it against the real AdenClean server on a throwaway
database, completes an actual request through the UI, photographs each screen, and
lays the shots out with a caption on the brand colours. Raw captures go to store/raw/.
Needs: Node and npm packages installed in mobile/, and Python with Playwright.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer

MOBILE = pathlib.Path(__file__).resolve().parents[1]
REPO = MOBILE.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("SESSION_SECRET", "x" * 48)

import main as server  # noqa: E402
import store as storage  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 5055
EXPORT = pathlib.Path(tempfile.mkdtemp(prefix="adenclean-web-"))
RAW = MOBILE / "store" / "raw"
OUT = MOBILE / "store" / "screenshots"
FONTS = MOBILE / "node_modules" / "@expo-google-fonts"
FOREST, PAPER, LIME = "#244B3F", "#F3F1E8", "#D6E28E"

PROFILES = {
    "ios-6.9": {"viewport": (440, 956), "scale": 3, "caption_px": 108},
    "android-phone": {"viewport": (360, 720), "scale": 3, "caption_px": 92},
}

CAPTIONS = [
    ("01-home", "A little more at ease at home."),
    ("02-service", "Pick the clean you need."),
    ("03-when", "Choose a day that suits you."),
    ("04-review", "Check it, then send it."),
    ("05-status", "See where your request stands."),
    ("06-feedback", "Tell us how it went."),
]


def build_web():
    env = {**os.environ, "EXPO_PUBLIC_API_URL": f"http://127.0.0.1:{PORT}", "EXPO_OFFLINE": "1", "CI": "1", "EXPO_NO_TELEMETRY": "1"}
    subprocess.run(["npx", "expo", "export", "--platform", "web", "--output-dir", str(EXPORT)], cwd=MOBILE, env=env, check=True,
                   stdout=subprocess.DEVNULL)


class Handler(server.AdenCleanHandler):
    """The real API, plus the exported app for every other path (single-page fallback)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        target = (EXPORT / clean.lstrip("/")).resolve()
        if str(target).startswith(str(EXPORT)) and target.is_file():
            return str(target)
        return str(EXPORT / "index.html")

    def log_message(self, *args):
        pass


def start_server():
    server.STORE = storage.SqliteStore(pathlib.Path(tempfile.mkdtemp()) / "shots.sqlite3")
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def api(path, payload):
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(request, timeout=10).read())


def seed():
    """Three earlier requests in different states, as a returning customer would have."""
    today = date.today()
    plan = [
        ("routine", 3, "morning", "completed"),
        ("deep", 6, "afternoon", "approved"),
        ("move-in/move-out", 11, "flexible", None),
    ]
    saved = []
    for index, (service, offset, time, status) in enumerate(plan):
        day = (today + timedelta(days=offset)).isoformat()
        sent = api("/api/service-requests", {
            "fullName": "Maya Alvarez", "email": "maya@example.com", "area": "Silver Spring", "serviceType": service,
            "preferredDate": day, "preferredTime": time, "notes": "", "consent": True,
        })
        if status:
            path = {"completed": ["approved", "completed"], "approved": ["approved"]}[status]
            current = "pending"
            for step in path:
                server.STORE.set_status("requests", sent["reference"], current, step, "2026-11-01T12:00:00+00:00", {
                    "record_type": "requests", "record_id": sent["reference"], "old_status": current,
                    "new_status": step, "note": "", "actor": "seed@example.com", "created_at": "2026-11-01T12:00:00+00:00"})
                current = step
        saved.append({
            "reference": sent["reference"], "token": sent["feedbackToken"],
            "createdAt": f"2026-10-2{index}T12:00:00.000Z", "service": service, "date": day, "time": time,
        })
    return saved


def seed_script(saved):
    items = json.dumps({f"adenclean.request.{s['reference']}": json.dumps(s) for s in saved})
    index = json.dumps(json.dumps([s["reference"] for s in saved]))
    return f"""
      (() => {{
        if (localStorage.getItem('adenclean.requests')) return;
        const items = {items};
        for (const [k, v] of Object.entries(items)) localStorage.setItem(k, v);
        localStorage.setItem('adenclean.requests', {index});
      }})();
    """


def capture(playwright, name, cfg, saved):
    width, height = cfg["viewport"]
    out = RAW / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=cfg["scale"],
                                  color_scheme="light", has_touch=True, is_mobile=True)
    context.add_init_script(seed_script(saved))
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None)

    def snap(label, wait=700):
        page.wait_for_timeout(wait)
        page.screenshot(path=str(out / f"{label}.png"))

    page.goto(f"http://127.0.0.1:{PORT}/")
    page.get_by_role("button", name="Request a cleaning").first.wait_for()
    snap("01-home", wait=2600)  # let the windows finish lighting up

    page.get_by_role("button", name="Request a cleaning").first.click()
    page.get_by_role("radio", name=re.compile("Routine home cleaning")).click()
    snap("02-service")
    page.get_by_role("button", name="Continue").click()

    page.get_by_role("radiogroup", name="Choose a day").get_by_role("radio").nth(3).click()
    page.get_by_role("radio", name="Morning").click()
    snap("03-when")
    page.get_by_role("button", name="Continue").click()

    page.get_by_label("Full name").fill("Maya Alvarez")
    page.get_by_label("Email address").fill("maya@example.com")
    page.get_by_label("Town or ZIP code").fill("Silver Spring")
    page.get_by_role("button", name="Continue").click()

    page.get_by_role("checkbox").click()
    snap("04-review")

    page.get_by_role("button", name="Send request").click()
    page.get_by_text("Request sent").wait_for()
    snap("05-status", wait=900)

    page.goto(f"http://127.0.0.1:{PORT}/requests")
    page.get_by_text("Your requests").wait_for()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "requests-list.png"))

    page.get_by_role("button", name=re.compile("Routine home cleaning, .*Completed")).first.click()
    page.get_by_text("Your review").wait_for()
    page.get_by_role("radio", name="5 stars").click()
    page.get_by_label("What was it like?").fill("Spotless kitchen and bathroom, and they were easy to talk to.")
    snap("06-feedback")

    # A dark-mode check for our own review, not for the store.
    dark = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2, color_scheme="dark")
    dark.add_init_script(seed_script(saved))
    dpage = dark.new_page()
    dpage.goto(f"http://127.0.0.1:{PORT}/")
    dpage.get_by_role("button", name="Request a cleaning").first.wait_for()
    dpage.wait_for_timeout(2600)
    dpage.screenshot(path=str(out / "dark-home.png"))

    browser.close()
    return errors


def verify_add_by_link(playwright, saved):
    """Paste a website-style private link into a fresh phone and check the request appears."""
    token = saved[0]["token"]  # the seeded request that is already completed
    browser = playwright.chromium.launch()
    page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    page.goto(f"http://127.0.0.1:{PORT}/requests")
    page.get_by_text("No requests yet").wait_for()
    page.get_by_label("Private link or code").fill("not a link")
    page.get_by_role("button", name="Add request").click()
    page.get_by_text("doesn't look like an AdenClean link").wait_for()
    page.get_by_label("Private link or code").fill(f"http://127.0.0.1:{PORT}/feedback.html#token={token}")
    page.get_by_role("button", name="Add request").click()
    page.get_by_role("button", name=re.compile("Routine home cleaning, .*Completed")).wait_for()
    page.get_by_role("button", name=re.compile("Routine home cleaning, .*Completed")).click()
    page.get_by_text("Your review").wait_for()
    assert page.get_by_text("Reference").count() == 0, "an imported request should not show a made-up reference"
    browser.close()
    print("add-by-link: ok")


def compose(playwright, name, cfg):
    width, height = cfg["viewport"][0] * cfg["scale"], cfg["viewport"][1] * cfg["scale"]
    # Final canvas is the same size as the raw capture; the shot is placed smaller inside it.
    out = OUT / name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    for index, (label, caption) in enumerate(CAPTIONS):
        dark = index % 2 == 0
        bg, fg, accent = (FOREST, PAPER, LIME) if dark else (PAPER, FOREST, FOREST)
        shot = (RAW / name / f"{label}.png").resolve().as_uri()
        pad = round(width * 0.075)
        # Every caption gets two lines of room so the phones line up; the phone is sized to
        # run off the bottom edge.
        top = pad + round(cfg["caption_px"] * 1.02 * 2) + round(pad * 0.8)
        ratio = cfg["viewport"][0] / cfg["viewport"][1]
        shot_w = min(int((height - top) * ratio) + 8, int(width * 0.92))
        html = f"""<!doctype html><meta charset=utf-8><style>
        @font-face {{ font-family:B; font-weight:800; src:url('file://{FONTS}/bricolage-grotesque/800ExtraBold/BricolageGrotesque_800ExtraBold.ttf'); }}
        html,body{{margin:0}} body{{width:{width}px;height:{height}px;overflow:hidden;background:{bg};position:relative}}
        .cap{{position:absolute;left:{pad}px;top:{pad}px;width:{width - 2 * pad}px;font-family:B,sans-serif;font-weight:800;
              font-size:{cfg['caption_px']}px;line-height:1.02;letter-spacing:-0.035em;color:{fg}}}
        .dot{{display:inline-block;width:0.2em;height:0.2em;border-radius:50%;background:{accent};margin-left:0.04em}}
        .shot{{position:absolute;left:{(width - shot_w) // 2}px;top:{top}px;width:{shot_w}px;border-radius:{round(width*0.07)}px {round(width*0.07)}px 0 0;
              border:{round(width*0.012)}px solid #0F1F1A;border-bottom:0;box-shadow:0 0 0 1px rgba(0,0,0,.08)}}
        </style><div class=cap>{caption}</div><img class=shot src="{shot}">"""
        holder = out / ".compose.html"
        holder.write_text(html, encoding="utf-8")
        page.goto(holder.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / f"{label}.png"))
        holder.unlink()
    browser.close()


def main():
    build_web()
    httpd = start_server()
    try:
        saved = seed()
        with sync_playwright() as pw:
            verify_add_by_link(pw, saved)
            for name, cfg in PROFILES.items():
                errors = capture(pw, name, cfg, saved)
                print(f"{name}: captured; browser errors: {errors or 'none'}")
                compose(pw, name, cfg)
                print(f"{name}: composed {len(CAPTIONS)} images ({cfg['viewport'][0]*cfg['scale']}x{cfg['viewport'][1]*cfg['scale']})")
    finally:
        httpd.shutdown()
        shutil.rmtree(EXPORT, ignore_errors=True)


if __name__ == "__main__":
    main()
