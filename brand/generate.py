"""Generates every Sibit brand asset from one geometry definition.

Mark: a geometric shield in two halves. The left half is solid; the right half
is drawn as stacked horizontal rule lines, with one line offset to the right
and highlighted in the accent colour — two versions compared, one rule changed.

    python brand/generate.py          (needs: pillow, fonttools, brotli; Inter from frontend/node_modules)

Outputs (brand/):
    sibit-mark.svg / sibit-mark-dark.svg              mark only (for light / dark backgrounds)
    sibit-logo.svg / sibit-logo-dark.svg              mark + "Sibit" wordmark (recommended, title case)
    sibit-logo-lowercase.svg / -lowercase-dark.svg    mark + "sibit" wordmark (alternative)
    favicon.svg                                       simplified 16px-optimised mark, adapts to theme
    sibit.ico                                         16/32/48/256 for Windows
    sibit-256.png                                     raster preview
and copies the web assets to frontend/public/brand/.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FONT = ROOT / "frontend" / "node_modules" / "@fontsource" / "inter" / "files" / "inter-latin-600-normal.woff2"

COLORS = {
    "light": {"primary": "#2563EB", "accent": "#0891B2", "text": "#0F172A"},
    "dark": {"primary": "#3B82F6", "accent": "#22D3EE", "text": "#E6EBF5"},
}

# --------------------------------------------------------------------------- #
# Geometry (64 x 64 grid)
# --------------------------------------------------------------------------- #
SHIELD = "M32 4 L54 10.5 V29 C54 43.5 45 53.5 32 60 C19 53.5 10 43.5 10 29 V10.5 Z"
SEAM_L, SEAM_R = 30.25, 33.75  # gap between the two halves


def bars(simple: bool) -> tuple[list[tuple[float, float]], int]:
    """(y, height) of each rule line, and the index of the highlighted one."""
    if simple:  # 16 px: three thick lines survive downscaling
        return [(13.0, 8.0), (26.0, 8.0), (39.0, 8.0)], 1
    return [(12.0, 5.0), (20.5, 5.0), (29.0, 5.0), (37.5, 5.0), (46.0, 5.0)], 2


OFFSET = 5.0  # how far the changed rule is shifted right
ACCENT_RIGHT = 60.0  # the changed rule pokes out of the shield


def _clip(poly: list[tuple[float, float]], x0: float, x1: float, y0: float, y1: float) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a convex polygon to an axis-aligned rectangle."""
    def edge(pts, inside, cross):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    pts = poly
    for inside, cross in ((lambda p: p[0] >= x0, at_x(x0)), (lambda p: p[0] <= x1, at_x(x1)),
                          (lambda p: p[1] >= y0, at_y(y0)), (lambda p: p[1] <= y1, at_y(y1))):
        pts = edge(pts, inside, cross)
        if not pts:
            break
    return pts


def _path(pts: list[tuple[float, float]]) -> str:
    return "M" + " L".join(f"{x:.2f} {y:.2f}".replace(".00", "") for x, y in pts) + " Z"


def mark_shapes(simple: bool) -> tuple[list[str], str, dict]:
    """(primary paths, accent rect attrs) — explicit geometry, no clipPath needed."""
    shield = shield_polygon()
    prim = [_path(_clip(shield, 0, SEAM_L, 0, 64))]
    ys, hi = bars(simple)
    for i, (y, h) in enumerate(ys):
        if i != hi:
            prim.append(_path(_clip(shield, SEAM_R, 64, y, y + h)))
    y, h = ys[hi]
    acc = {"x": SEAM_R + OFFSET, "y": y, "width": ACCENT_RIGHT - SEAM_R - OFFSET, "height": h, "rx": h / 2}
    return prim, "", acc


def _acc_rect(a: dict, attr: str) -> str:
    return (f'<rect x="{a["x"]:g}" y="{a["y"]:g}" width="{a["width"]:g}" height="{a["height"]:g}" '
            f'rx="{a["rx"]:g}" {attr}/>')


def mark_svg_body(c: dict, simple: bool = False, idp: str = "s") -> str:
    prim, _, acc = mark_shapes(simple)
    return f'<path d="{" ".join(prim)}" fill="{c["primary"]}"/>' + _acc_rect(acc, f'fill="{c["accent"]}"')


def svg(w: float, h: float, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n')


# --------------------------------------------------------------------------- #
# Wordmark: Inter SemiBold outlines, tracking -0.02em
# --------------------------------------------------------------------------- #
def wordmark_path(text: str, size: float, x0: float, baseline: float) -> tuple[str, float, float]:
    font = TTFont(str(FONT))
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    tracking = -0.02 * upm
    hmtx = font["hmtx"]
    pen = SVGPathPen(gs)
    x = 0.0
    bp = BoundsPen(gs)
    for ch in text:
        g = cmap[ord(ch)]
        t = TransformPen(pen, (scale, 0, 0, -scale, x0 + x * scale, baseline))
        gs[g].draw(t)
        gs[g].draw(TransformPen(bp, (1, 0, 0, 1, x, 0)))
        x += hmtx[g][0] + tracking
    width = (x - tracking) * scale
    cap = font["OS/2"].sCapHeight * scale
    return pen.getCommands(), width, cap


def logo_svg(c: dict, text: str) -> str:
    size = 42.0
    gap = 14.0
    # Vertically centre the cap height on the mark's optical centre (y = 32).
    _, _, cap = wordmark_path(text, size, 0, 0)
    baseline = 32 + cap / 2
    d, width, _ = wordmark_path(text, size, 64 + gap, baseline)
    w = 64 + gap + width + 2
    body = mark_svg_body(c, idp="l") + f'<path d="{d}" fill="{c["text"]}"/>'
    return svg(round(w, 1), 64, body, "Sibit")


def favicon_svg() -> str:
    lc, dc = COLORS["light"], COLORS["dark"]
    style = (f"<style>.p{{fill:{lc['primary']}}}.a{{fill:{lc['accent']}}}"
             f"@media (prefers-color-scheme:dark){{.p{{fill:{dc['primary']}}}.a{{fill:{dc['accent']}}}}}</style>")
    prim, _, acc = mark_shapes(True)
    return svg(64, 64, style + f'<path class="p" fill="{lc["primary"]}" d="{" ".join(prim)}"/>'
               + _acc_rect(acc, f'class="a" fill="{lc["accent"]}"'), "Sibit")


# --------------------------------------------------------------------------- #
# Raster (ICO) — same geometry, drawn with Pillow at 16x supersampling
# --------------------------------------------------------------------------- #
def _bezier(p0, p1, p2, p3, n=48):
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
                    mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]))
    return out


def shield_polygon() -> list[tuple[float, float]]:
    pts = [(32, 4), (54, 10.5), (54, 29)]
    pts += _bezier((54, 29), (54, 43.5), (45, 53.5), (32, 60))[1:]
    pts += _bezier((32, 60), (19, 53.5), (10, 43.5), (10, 29))[1:]
    pts += [(10, 10.5)]
    return pts


def render_png(px: int, c: dict, simple: bool) -> Image.Image:
    ss = 16
    S = px * ss
    k = S / 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon([(x * k, y * k) for x, y in shield_polygon()], fill=255)
    shapes = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(shapes)
    d.rectangle([0, 0, SEAM_L * k, S], fill=255)
    ys, hi = bars(simple)
    for i, (y, h) in enumerate(ys):
        if i != hi:
            d.rectangle([SEAM_R * k, y * k, S, (y + h) * k], fill=255)
    clipped = Image.composite(shapes, Image.new("L", (S, S), 0), mask)
    img.paste(Image.new("RGBA", (S, S), c["primary"]), (0, 0), clipped)
    y, h = ys[hi]
    acc = Image.new("L", (S, S), 0)
    ImageDraw.Draw(acc).rounded_rectangle(
        [(SEAM_R + OFFSET) * k, y * k, ACCENT_RIGHT * k, (y + h) * k], radius=h / 2 * k, fill=255)
    img.paste(Image.new("RGBA", (S, S), c["accent"]), (0, 0), acc)
    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    out = HERE
    for mode in ("light", "dark"):
        c = COLORS[mode]
        sfx = "" if mode == "light" else "-dark"
        (out / f"sibit-mark{sfx}.svg").write_text(svg(64, 64, mark_svg_body(c), "Sibit"), encoding="utf-8")
        (out / f"sibit-logo{sfx}.svg").write_text(logo_svg(c, "Sibit"), encoding="utf-8")
        (out / f"sibit-logo-lowercase{sfx}.svg").write_text(logo_svg(c, "sibit"), encoding="utf-8")
    (out / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")

    # Windows icon: the dark-theme palette reads well on both light and dark taskbars.
    c = COLORS["dark"]
    sizes = [16, 32, 48, 256]
    imgs = {s: render_png(s, c, simple=s <= 32) for s in sizes}
    imgs[256].save(out / "sibit.ico", format="ICO", sizes=[(s, s) for s in sizes],
                   append_images=[imgs[s] for s in sizes if s != 256])
    imgs[256].save(out / "sibit-256.png")
    render_png(32, c, simple=True).save(out / "sibit-32.png")

    web = ROOT / "frontend" / "public" / "brand"
    web.mkdir(parents=True, exist_ok=True)
    for f in ("sibit-mark.svg", "sibit-mark-dark.svg", "sibit-logo.svg", "sibit-logo-dark.svg"):
        shutil.copy(out / f, web / f)
    shutil.copy(out / "favicon.svg", ROOT / "frontend" / "public" / "favicon.svg")
    print("brand assets written to", out)


if __name__ == "__main__":
    main()
