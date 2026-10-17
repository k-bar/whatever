"""Generates the Warsaw mermaid (Syrenka) icon set.

All artwork is hand-drawn as SVG paths in one shared geometry, so every
variation keeps the exact same silhouette. Run from frontend/:  python3 scripts/mermaid_generate.py
Writes the SVGs and variants.json to public/mermaid/; preview them with scripts/mermaid_gallery.html.
"""
import re
from pathlib import Path

OUT = Path(__file__).parent.parent / "public" / "mermaid"

_TOK = re.compile(r"[MLCQHVZ]|-?\d*\.?\d+")


def affine(d, a=1, b=0, c=0, dd=1, e=0, f=0):
    """Apply x'=a*x+c*y+e, y'=b*x+dd*y+f to a path of absolute commands."""
    toks, out, i, x0, y0 = _TOK.findall(d), [], 0, 0.0, 0.0
    pt = lambda x, y: f"{a*x+c*y+e:.1f},{b*x+dd*y+f:.1f}"
    while i < len(toks):
        t = toks[i]; i += 1
        if t in "MLCQ":
            vals = []
            while i < len(toks) and toks[i] not in "MLCQHVZ":
                vals.append(float(toks[i])); i += 1
            pairs = list(zip(vals[::2], vals[1::2]))
            x0, y0 = pairs[-1]
            out.append(t + " ".join(pt(x, y) for x, y in pairs))
        elif t in "HV":
            v = float(toks[i]); i += 1
            x0, y0 = (v, y0) if t == "H" else (x0, v)
            out.append("L" + pt(x0, y0))
        elif t == "Z":
            out.append("Z")
    return " ".join(out)


def scale(d, sx, sy=None, ox=0, oy=0, tx=0, ty=0):
    sy = sx if sy is None else sy
    return affine(d, sx, 0, 0, sy, ox - sx * ox + tx, oy - sy * oy + ty)

# ---------------------------------------------------------------------------
# Geometry. Mermaid parts are in shield-local space (shield = 320 x 440,
# origin top-left); the shield itself sits at (40,150) in a 400-wide artboard.
# ---------------------------------------------------------------------------

SHIELD = ("M0,0 H320 V350 C320,398 292,418 232,422 "
          "C196,424 172,430 160,440 C148,430 124,424 88,422 "
          "C28,418 0,398 0,350 Z")

BODY = ("M132,60 C120,59 112,66 112,74 C112,77 110,79 109,81 L104,88 "
        "C104,90 106,91 108,91 C108,93 107,95 108,96 C107,98 108,100 110,102 "
        "C112,104 116,105 119,105 L121,112 C120,116 116,119 112,122 "
        "C108,130 100,140 101,148 C102,154 108,157 112,158 "
        "C113,172 117,182 117,190 C117,197 115,202 113,206 L169,206 "
        "C167,200 164,194 164,188 C165,172 174,158 173,140 C172,130 168,124 160,120 "
        "C153,117 148,113 147,107 C149,96 151,88 149,80 C147,68 140,61 132,60 Z")

BACK_ARM = ("M156,122 C170,128 184,140 194,156 L200,166 L188,176 "
            "C178,162 168,152 158,148 Z")

HAIR = ("M112,70 C111,60 123,53 138,54 C150,55 160,59 168,64 "
        "C178,70 185,78 185,86 C185,92 181,95 176,96 "
        "C181,100 181,107 176,111 C169,115 160,113 153,110 "
        "C151,101 148,92 142,87 C134,80 124,73 112,70 Z")

RAISED_ARM = ("M130,118 L74.6,90.6 L97.8,58.6 C103,57 107,52 106,46 "
              "C106,40 101,36 96,36 C90,36 86,40 86,46 L88.2,51.4 "
              "L58.8,90.1 C55,95 56,100 61,100.5 L118,134 Z")

FIST = "M106,46 C106,40 101,36 96,36 C90,36 86,40 86,46 C86,52 91,57 97,57 C102,57 106,52 106,46 Z"

SABER = "M104,41 C150,18 208,34 228,98 C202,48 152,34 108,50 Z"
GUARD = "M104,32 L110,31 L114,56 L108,57 Z"
POMMEL = "M80,49 C80,46 82,44 85,44 C88,44 89,47 89,49 C89,52 87,54 85,54 C82,54 80,52 80,49 Z"

TAIL = ("M110,199 C130,193 152,193 171,199 "
        "C179,230 181,270 179,300 C177,326 184,346 198,350 "
        "C213,353 224,340 228,322 L230,306 "
        "C226,292 220,276 211,261 "
        "C225,271 239,281 250,289 "
        "C262,277 276,265 293,255 "
        "C287,277 271,298 253,311 "
        "C249,338 240,368 216,386 "
        "C192,403 152,407 122,394 "
        "C84,378 63,344 66,304 "
        "C68,264 90,224 110,199 Z")

FLUKE_RIBS = ("M236,304 L221,270 M242,301 L238,282 M247,301 L266,273 "
              "M251,305 L282,266")

BUCKLER = (222, 172, 50)  # cx, cy, r (shield-local)

def tr(x=40, y=150):
    return f'transform="translate({x},{y})"'


def circle(cx, cy, r, **a):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" {attrs(a)}/>'


def path(d, **a):
    return f'<path d="{d}" {attrs(a)}/>'


def attrs(a):
    return " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in a.items() if v is not None)


# ---------------------------------------------------------------------------
# Final placement: shorten the tail to the official proportion, then scale the
# whole figure to fill the shield.
# ---------------------------------------------------------------------------
_K, _CX, _TOP = 1.12, 152, 24


def _place(d):
    return affine(d, _K, 0, 0, _K, _CX - _K * 170, _TOP - _K * 18)


def parts():
    tail = scale(TAIL, 0.95, 0.74, ox=140, oy=200)
    ribs = scale(FLUKE_RIBS, 0.95, 0.74, ox=140, oy=200)
    cx, cy, r = BUCKLER
    p = {k: _place(v) for k, v in dict(
        body=BODY, back_arm=BACK_ARM, hair=HAIR, arm=RAISED_ARM, fist=FIST,
        saber=SABER, guard=GUARD, pommel=POMMEL, tail=tail, ribs=ribs).items()}
    p["buckler"] = (_K * (cx - 170) + _CX, _K * (cy - 18) + _TOP, _K * r)
    return p


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
import math

GROW = 'transform="translate(200,138) scale(1.3) translate(-200,-138)"'


def crown_simple(fill, ink=None, iw=0, grow=0):
    """Modern crown from the city's visual identity: three rings on a band.
    Drawn in layers so an outline (ink) wraps the union; grow fattens every
    shape (used for the sticker halo)."""
    def layer(c, extra):
        return (f'<circle cx="160" cy="98" r="23" fill="none" stroke="{c}" stroke-width="{14 + extra}"/>'
                f'<circle cx="240" cy="98" r="23" fill="none" stroke="{c}" stroke-width="{14 + extra}"/>'
                f'<circle cx="200" cy="90" r="28" fill="none" stroke="{c}" stroke-width="{15 + extra}"/>'
                f'<rect x="128" y="112" width="144" height="26" rx="4" fill="{c}" stroke="{c}" stroke-width="{extra}" stroke-linejoin="round"/>'
                f'<path d="M195,38 h10 v10 h10 v10 h-10 v8 h-10 v-8 h-10 v-10 h10 z" fill="{c}" stroke="{c}" stroke-width="{extra}" stroke-linejoin="round"/>')
    out = layer(ink, 2 * iw + grow) if ink else ""
    out += layer(fill, grow)
    return f'<g class="crown" {GROW}>{out}</g>'


def _bez(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d
                 for a, b, c, d in zip(p0, p1, p2, p3))


def crown_heraldic(gold, gold_dark, velvet, ruby, sapphire, pearl, ink, iw):
    """Traditional closed royal crown, as on the historic coat of arms."""
    s = dict(stroke=ink, stroke_width=iw, stroke_linejoin="round")
    arches = [((134, 116), (130, 86), (160, 64), (200, 62)),
              ((266, 116), (270, 86), (240, 64), (200, 62)),
              ((168, 116), (166, 92), (182, 70), (200, 62)),
              ((232, 116), (234, 92), (218, 70), (200, 62))]
    out = [path("M128,118 C126,78 160,58 200,58 C240,58 274,78 272,118 Z", fill=velvet, **s)]
    for w, c in ((9 + 2 * iw, ink), (9, gold)):
        for a in arches:
            d = "M{},{} C{},{} {},{} {},{}".format(*a[0], *a[1], *a[2], *a[3])
            out.append(path(d, fill="none", stroke=c, stroke_width=w, stroke_linecap="round"))
        out.append(path("M200,116 L200,62", fill="none", stroke=c, stroke_width=w, stroke_linecap="round"))
    for a in arches[:2]:
        for t in (0.12, 0.3, 0.48, 0.66, 0.84):
            x, y = _bez(*a, t)
            out.append(circle(f"{x:.1f}", f"{y:.1f}", 2.6, fill=pearl, stroke=ink, stroke_width=iw * 0.5))
    out.append(circle(200, 52, 10, fill=gold, **s))
    out.append(path("M196,20 h8 v10 h9 v8 h-9 v8 h-8 v-8 h-9 v-8 h9 z", fill=gold, **s))
    for x in (151, 184, 216, 249):
        out.append(path(f"M{x},94 L{x+7},106 L{x},113 L{x-7},106 Z", fill=gold, **s))
    out.append(f'<rect x="118" y="112" width="164" height="30" rx="5" fill="{gold}" stroke="{ink}" stroke-width="{iw}"/>')
    out.append(path("M122,118 H278 M122,136 H278", fill="none", stroke=gold_dark, stroke_width=1.6))
    for x in (159, 200, 241):
        out.append(f'<ellipse cx="{x}" cy="127" rx="8" ry="5.5" fill="{ruby}" stroke="{ink}" stroke-width="{iw * 0.6}"/>')
    for x in (138, 180, 220, 262):
        out.append(circle(x, 127, 3.6, fill=sapphire, stroke=ink, stroke_width=iw * 0.6))
    return '<g class="crown">' + "".join(out) + "</g>"


def _wedge(cx, cy, r0, r1, a0, a1):
    p = lambda r, a: f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}"
    return (f"M{p(r0, a0)} L{p(r1, a0)} A{r1},{r1} 0 0 1 {p(r1, a1)} "
            f"L{p(r0, a1)} A{r0},{r0} 0 0 0 {p(r0, a0)} Z")


def buckler(cx, cy, r, base, light=None, dark=None, ink=None, iw=0, rays=0, rings=True):
    """Round shield. Optional sunburst rays and rings, as on the historic arms."""
    out = [circle(f"{cx:.1f}", f"{cy:.1f}", f"{r:.1f}", fill=base, stroke=ink,
                  stroke_width=iw if ink else None)]
    if rays:
        step = 2 * math.pi / rays
        d = " ".join(_wedge(cx, cy, r * 0.2, r * 0.84, i * step, i * step + step / 2)
                     for i in range(0, rays))
        out.append(path(d, fill=light))
    if rings and dark:
        out.append(circle(f"{cx:.1f}", f"{cy:.1f}", f"{r * 0.84:.1f}", fill="none", stroke=dark, stroke_width=f"{r * 0.05:.1f}"))
        out.append(circle(f"{cx:.1f}", f"{cy:.1f}", f"{r * 0.55:.1f}", fill="none", stroke=dark, stroke_width=f"{r * 0.035:.1f}"))
        out.append(circle(f"{cx:.1f}", f"{cy:.1f}", f"{r * 0.18:.1f}", fill=light or base, stroke=dark, stroke_width=f"{r * 0.04:.1f}"))
    return "".join(out)


def scales_pattern(pid, color, sw=1.3):
    return (f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="22" height="14">'
            f'<path d="M0,0 A11,11 0 0 0 22,0 M-11,7 A11,11 0 0 0 11,7 M11,7 A11,11 0 0 0 33,7 '
            f'M0,14 A11,11 0 0 0 22,14" fill="none" stroke="{color}" stroke-width="{sw}"/></pattern>')


def figure(c, ink=None, iw=0, scales=None, ribs=None, rays=0, buckler_rings=True):
    """The mermaid in shield-local space. c: dict of fills
    (body, hair, tail, saber, buckler, buckler_light, buckler_dark)."""
    P = parts()
    s = dict(stroke=ink, stroke_width=iw if ink else None,
             stroke_linejoin="round" if ink else None)
    out = [path(P["back_arm"], fill=c["body"], **s),
           buckler(*P["buckler"], c["buckler"], c.get("buckler_light"),
                   c.get("buckler_dark"), ink, iw, rays, buckler_rings),
           path(P["body"], fill=c["body"], **s),
           path(P["tail"], fill=c["tail"], **s)]
    if scales:
        out.append(path(P["tail"], fill=f"url(#{scales})"))
    if ribs:
        out.append(path(P["ribs"], fill="none", stroke=ribs, stroke_width=1.6, stroke_linecap="round"))
    if scales and ink:
        out.append(path(P["tail"], fill="none", **s))
    out += [path(P["hair"], fill=c["hair"], **s),
            path(P["saber"], fill=c["saber"], **s),
            path(P["guard"], fill=c["saber"], **s),
            path(P["pommel"], fill=c["saber"], **s),
            path(P["arm"], fill=c["body"], **s)]
    return "".join(out)


def shield(fill, stroke=None, sw=0, inner=None):
    out = path(SHIELD, fill=fill, stroke=stroke, stroke_width=sw if stroke else None,
               stroke_linejoin="round" if stroke else None)
    if inner:  # thin inset keyline
        out += path(scale(SHIELD, 0.94, 0.95, ox=160, oy=210), fill="none",
                    stroke=inner[0], stroke_width=inner[1], opacity=inner[2])
    return out


# viewBoxes (artboard: shield 40..360 x 150..590, crown up to y=3)
V_PORTRAIT = "24 4 352 602"
V_SQ_CROWN = "-121.5 -25 643 643"
V_TILE_CROWN = "-175 -78 750 750"
V_SQ_SHIELD = "-60 110 520 520"
V_TILE_SHIELD = "-110 60 620 620"


def tile(view, fill, stroke=None):
    x, y, w, h = map(float, view.split())
    st = f' stroke="{stroke}" stroke-width="2"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{w * 0.225:.1f}" fill="{fill}"{st}/>'


def svg(view, title, body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" '
            f'aria-label="{title}"><title>{title}</title>'
            + (f"<defs>{defs}</defs>" if defs else "") + body + "</svg>\n")


def lin(gid, c0, c1, x2=0, y2=1, extra=""):
    return (f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}"{extra}>'
            f'<stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/></linearGradient>')


# ---------------------------------------------------------------------------
# Variations
# ---------------------------------------------------------------------------
RED, GOLD, WHITE = "#D9392B", "#F2C14E", "#FFFFFF"
VARIANTS = []


def variant(fn):
    VARIANTS.append(fn)
    return fn


@variant
def v00():
    """Heraldic master: the full historic arms, redrawn crisp."""
    ink = "#4A1610"
    defs = scales_pattern("sc", "#C2901F", 1.2)
    c = dict(body="#FFFDF8", hair="#F5C542", tail="#F6D24E", saber="#FFFDF8",
             buckler="#EF8F2F", buckler_light="#F8CF52", buckler_dark="#B5501C")
    body = (crown_heraldic("#F4C542", "#C2901F", "#B3261E", "#C8232C", "#3E8EDE", "#FFFDF8", ink, 2)
            + f'<g {tr()}>' + shield("#D6352B", ink, 3)
            + figure(c, ink, 2, scales="sc", ribs="#C2901F", rays=16) + "</g>")
    return "00-heraldic-master", "Heraldic master", "The historic arms 1:1: closed royal crown, scaled tail, sunburst shield.", svg(V_PORTRAIT, "Warsaw mermaid, heraldic", body, defs)


@variant
def v01():
    c = dict(body=WHITE, hair=GOLD, tail=GOLD, saber=WHITE, buckler=GOLD)
    body = crown_simple(GOLD) + f'<g {tr()}>' + shield(RED) + figure(c) + "</g>"
    return "01-flat-official", "Flat official", "No outlines, the city's three colours. The baseline.", svg(V_SQ_CROWN, "Warsaw mermaid, flat", body)


@variant
def v02():
    red, bg = "#D33A2C", "#FFF8F1"
    c = dict(body=bg, hair=bg, tail=bg, saber=bg, buckler=bg, buckler_dark=red)
    body = (tile(V_TILE_CROWN, bg) + crown_simple(red) + f'<g {tr()}>' + shield(bg, red, 10)
            + figure(c, red, 6) + "</g>")
    return "02-line", "Line", "Single-weight outline on cream. Light, editorial.", svg(V_TILE_CROWN, "Warsaw mermaid, line", body)


@variant
def v03():
    defs = (lin("sh", "#F2603F", "#B71F2B") + lin("gd", "#FFE38F", "#E8A436")
            + lin("bd", "#FFFFFF", "#FFEBDD")
            + lin("gl", "#FFFFFF", "#FFFFFF", extra=' gradientUnits="objectBoundingBox"').replace(
                '<stop offset="1" stop-color="#FFFFFF"/>', '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>').replace(
                '<stop offset="0" stop-color="#FFFFFF"/>', '<stop offset="0" stop-color="#FFFFFF" stop-opacity=".22"/>'))
    c = dict(body="url(#bd)", hair="url(#gd)", tail="url(#gd)", saber="url(#bd)", buckler="url(#gd)")
    gloss = path("M0,0 H320 V150 C220,185 100,185 0,150 Z", fill="url(#gl)")
    body = (crown_simple("url(#gd)") + f'<g {tr()}>' + shield("url(#sh)") + gloss
            + figure(c) + "</g>")
    return "03-gradient", "Gradient", "Warm red-to-crimson shield, gilded tail and crown, soft top light.", svg(V_SQ_CROWN, "Warsaw mermaid, gradient", body, defs)


@variant
def v04():
    red = "#D6302A"
    c = dict(body=WHITE, hair=WHITE, tail=WHITE, saber=WHITE, buckler=WHITE, buckler_dark=red)
    body = (f'<g {tr()}>' + shield(red) + figure(c, red, 5) + "</g>")
    return "04-knockout", "Bold knockout", "One colour cut out of the shield; red gaps separate the parts. Built for 16-32px.", svg(V_SQ_SHIELD, "Warsaw mermaid, knockout", body)


@variant
def v05():
    sh, cream, sand, sand2 = "#E8806F", "#FFF8EF", "#F2D49A", "#EDC67F"
    c = dict(body=cream, hair=sand, tail=sand2, saber=cream, buckler=sand)
    body = (tile(V_TILE_CROWN, "#FBEDE7") + crown_simple(sand2) + f'<g {tr()}>' + shield(sh)
            + figure(c) + "</g>")
    return "05-pastel", "Pastel", "Coral, cream and sand. The gentle version.", svg(V_TILE_CROWN, "Warsaw mermaid, pastel", body)


@variant
def v06():
    ink, red, gold = "#2A1712", "#E2412F", "#FFC93F"
    defs = '<filter id="ds" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#2A1712" flood-opacity=".25"/></filter>'
    c = dict(body=WHITE, hair=gold, tail=gold, saber=WHITE, buckler=gold, buckler_dark=ink)
    halo = crown_simple(WHITE, grow=20)
    halo_shield = f'<g {tr()}>' + path(SHIELD, fill=WHITE, stroke=WHITE, stroke_width=26, stroke_linejoin="round") + "</g>"
    body = (f'<g filter="url(#ds)">{halo}{halo_shield}</g>' + crown_simple(gold, ink, 3)
            + f'<g {tr()}>' + shield(red, ink, 6) + figure(c, ink, 4) + "</g>")
    return "06-ink-sticker", "Ink sticker", "Thick ink outlines, punchy fills, white die-cut border.", svg(V_TILE_CROWN, "Warsaw mermaid, sticker", body, defs)


@variant
def v07():
    defs = lin("bg", "#E4462F", "#A61C26", 0.6, 1)
    cream, red, gold = "#FFF6E9", "#D6342A", "#F0B847"
    c = dict(body=red, hair=gold, tail=red, saber=red, buckler=gold)
    body = (tile(V_TILE_CROWN, "url(#bg)") + crown_simple(cream) + f'<g {tr()}>'
            + shield(cream, gold, 8) + figure(c) + "</g>")
    return "07-app-tile", "App tile", "Inverted: red mermaid on a cream shield, on a red rounded tile.", svg(V_TILE_CROWN, "Warsaw mermaid, app tile", body, defs)


@variant
def v08():
    defs = (lin("bg", "#222B4D", "#0D1226", 0.4, 1) + lin("sh", "#D2392D", "#8C1A24")
            + lin("gd", "#FFE7A3", "#E9A63B"))
    c = dict(body="#FFF3DE", hair="url(#gd)", tail="url(#gd)", saber="#FFF3DE", buckler="url(#gd)")
    stars = "".join(path(f"M{x},{y-r} Q{x},{y} {x+r},{y} Q{x},{y} {x},{y+r} Q{x},{y} {x-r},{y} Q{x},{y} {x},{y-r} Z",
                         fill="#FFE7A3", opacity=o)
                    for x, y, r, o in ((-90, 60, 14, .9), (480, 150, 10, .7), (-60, 560, 8, .5), (455, 520, 12, .8)))
    body = (tile(V_TILE_CROWN, "url(#bg)") + stars + crown_simple("url(#gd)") + f'<g {tr()}>'
            + shield("url(#sh)", "#F2C14E", 4) + figure(c) + "</g>")
    return "08-night", "Night", "Warszawa never sleeps: crimson shield and gold on midnight navy.", svg(V_TILE_CROWN, "Warsaw mermaid, night", body, defs)


@variant
def v09():
    red = "#C92F27"
    c = dict(body=red, hair=red, tail=red, saber=red, buckler=red, buckler_dark=WHITE)
    body = (crown_simple(red) + f'<g {tr()}>' + shield(WHITE, red, 9)
            + figure(c, WHITE, 4) + "</g>")
    return "09-mono", "Mono stamp", "Single red ink on white. For print, stamps and favicons.", svg(V_SQ_CROWN, "Warsaw mermaid, mono", body)


if __name__ == "__main__":
    meta = []
    for fn in VARIANTS:
        slug, name, note, content = fn()
        (OUT / f"{slug}.svg").write_text(content)
        meta.append((slug, name, note))
        print("wrote", slug)
    import json
    (OUT / "variants.json").write_text(json.dumps(
        [dict(file=f"{s}.svg", name=n, note=t) for s, n, t in meta], indent=2) + "\n")
