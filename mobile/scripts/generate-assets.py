"""Draws the AdenClean app icon, splash images and store graphics from one SVG house.

    python scripts/generate-assets.py

Needs Python with Playwright and Chromium. Outputs go to assets/images and store/.
"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG = ROOT / "assets" / "images"
STORE = ROOT / "store"
FONTS = ROOT / "node_modules" / "@expo-google-fonts"
IMG.mkdir(parents=True, exist_ok=True)
STORE.mkdir(parents=True, exist_ok=True)

FOREST, PAPER, LIME, INK, DEEP = "#244B3F", "#F3F1E8", "#D6E28E", "#1C3B32", "#0F1F1A"

WINDOWS = [(58, 92, 30, 28), (112, 92, 30, 28), (44, 134, 32, 28), (124, 134, 32, 28)]


def house(outline, windows, sparkle, stroke=5, win_fill=LIME, window_stroke=None):
    """The house as SVG markup in a 200 x 190 box."""
    w = "".join(
        f'<rect x="{x}" y="{y}" width="{ww}" height="{h}" rx="6" fill="{win_fill}"'
        + (f' stroke="{window_stroke}" stroke-width="{stroke}"' if window_stroke else "")
        + "/>"
        for x, y, ww, h in WINDOWS
    ) if windows else ""
    sp = (
        f'<path d="M152 36l9-8M166 50l10-3M100 10V2" stroke="{sparkle}" stroke-width="{stroke}" stroke-linecap="round"/>'
        if sparkle
        else ""
    )
    return (
        f'<g fill="none" stroke="{outline}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 92 100 24l80 68"/>'
        '<path d="M34 82v84a8 8 0 0 0 8 8h116a8 8 0 0 0 8-8V82"/>'
        '<rect x="88" y="126" width="24" height="48" rx="5"/>'
        "</g>" + w + sp
    )


def svg_page(size_w, size_h, body_svg, bg=None, extra_css="", extra_html=""):
    background = f"background:{bg};" if bg else "background:transparent;"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    @font-face {{ font-family:'Bricolage'; font-weight:800; src:url('file://{FONTS}/bricolage-grotesque/800ExtraBold/BricolageGrotesque_800ExtraBold.ttf'); }}
    @font-face {{ font-family:'Figtree'; font-weight:500; src:url('file://{FONTS}/figtree/500Medium/Figtree_500Medium.ttf'); }}
    html,body{{margin:0;padding:0;}} body{{width:{size_w}px;height:{size_h}px;overflow:hidden;{background}{extra_css}}}
    svg{{display:block}}
    </style></head><body>{body_svg}{extra_html}</body></html>"""


def centered(size, scale, inner, bg=None, dx=0, dy=0):
    """Place the 200x190 house, scaled, in the middle of a square canvas."""
    w, h = 200 * scale, 190 * scale
    ox, oy = (size - w) / 2 + dx, (size - h) / 2 + dy
    return svg_page(
        size, size,
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        + (f'<rect width="{size}" height="{size}" fill="{bg}"/>' if bg else "")
        + f'<g transform="translate({ox} {oy}) scale({scale})">{inner}</g></svg>',
    )


def shoot(page, html, path, w, h, transparent=False):
    # Load from a real file: a page built in memory may not read local fonts or images.
    page.set_viewport_size({"width": w, "height": h})
    holder = ROOT / "store" / ".page.html"
    holder.write_text(html, encoding="utf-8")
    page.goto(holder.as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(250)
    page.screenshot(path=str(path), omit_background=transparent)
    print("wrote", path.relative_to(ROOT))


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(device_scale_factor=1)

    # iOS icon: opaque, full-bleed. The house is bold and the four windows are lit.
    shoot(page, centered(1024, 4.1, house(PAPER, True, LIME, stroke=6), bg=FOREST, dy=18), IMG / "icon.png", 1024, 1024)

    # Android adaptive icon: the house stays inside the centre safe zone.
    shoot(page, centered(1024, 3.1, house(PAPER, True, LIME, stroke=6), dy=16), IMG / "android-icon-foreground.png", 1024, 1024, True)
    shoot(page, centered(1024, 1, "", bg=FOREST), IMG / "android-icon-background.png", 1024, 1024)
    # Themed (monochrome) icon: one colour, solid windows.
    shoot(page, centered(1024, 3.1, house("#FFFFFF", True, "#FFFFFF", stroke=6, win_fill="#FFFFFF"), dy=16), IMG / "android-icon-monochrome.png", 1024, 1024, True)

    # Splash: just the house, lit, on the launch colour. Light and dark variants.
    shoot(page, centered(1024, 3.4, house(FOREST, True, FOREST, stroke=6, win_fill=LIME, window_stroke=FOREST), dy=10), IMG / "splash-icon.png", 1024, 1024, True)
    shoot(page, centered(1024, 3.4, house(PAPER, True, LIME, stroke=6), dy=10), IMG / "splash-icon-dark.png", 1024, 1024, True)

    # Web favicon.
    shoot(page, centered(48, 0.2, house(PAPER, True, LIME, stroke=9), bg=FOREST), IMG / "favicon.png", 48, 48)

    # Play Store hi-res icon (512) comes from the iOS icon.
    shoot(page, centered(512, 2.05, house(PAPER, True, LIME, stroke=6), bg=FOREST, dy=9), STORE / "play-icon-512.png", 512, 512)

    # Play Store feature graphic, 1024 x 500.
    feature = svg_page(
        1024, 500,
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="500" viewBox="0 0 1024 500">'
        f'<rect width="1024" height="500" fill="{FOREST}"/>'
        f'<g transform="translate(560 8) scale(2.7)">{house(PAPER, True, LIME, stroke=5)}</g></svg>',
        extra_html=f"""<div style="position:absolute;left:64px;top:118px;width:470px;color:{PAPER};font-family:Bricolage,sans-serif;font-weight:800;font-size:64px;line-height:1.04;letter-spacing:-2px">A little more at ease at home.</div>
        <div style="position:absolute;left:66px;top:340px;width:540px;color:{LIME};font-family:Figtree,sans-serif;font-weight:500;font-size:27px;line-height:1.3">Request a home cleaning in a minute.</div>
        <div style="position:absolute;left:64px;top:52px;color:{PAPER};font-family:Bricolage,sans-serif;font-weight:800;font-size:30px;letter-spacing:-1px">aden<span style="color:{LIME}">clean</span></div>""",
    )
    shoot(page, feature, STORE / "play-feature-graphic-1024x500.png", 1024, 500)

    browser.close()
    (ROOT / "store" / ".page.html").unlink(missing_ok=True)
