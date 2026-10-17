"""Build the busy-area outlines: where in Warsaw you are most likely to bump into people.

Method (stdlib only, no numpy/shapely):
    1. Pull social venues, squares, pedestrian streets and stations for Warsaw from
       OpenStreetMap (Overpass API). Cached in _cache/osm.json; pass --refresh to re-download.
    2. Every thing gets a weight (a nightclub draws more people than a fast-food stand; a
       pedestrian street counts once every 25 m) and is splatted onto a 40 m grid with a
       Gaussian kernel -> a "social density" surface. Pedestrian streets and sights can at most
       double the density that venues already create (see BOOSTERS).
    3. Marching squares traces the density at two thresholds into detailed outlines:
       level "busy" (the area) and level "very_busy" (its core). Outlines are simplified
       (Douglas-Peucker) and smoothed (Chaikin) so they read as organic shapes on the map.
    4. Each area is named after the streets most of its venues are on, and described by its mix.

Output:
    backend/busyareas/busy_areas.geojson          served as GET /busyareas
    frontend/public/mock/busy_areas.geojson       frontend fallback while the API is down

Usage:
    python3 backend/busyareas/build_busy_areas.py [--refresh] [--busy 18] [--very 45] [--stats]
"""

import argparse
import json
import math
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CACHE = HERE / "_cache" / "osm.json"
OUT = HERE / "busy_areas.geojson"
MOCK_OUT = ROOT / "frontend" / "public" / "mock" / "busy_areas.geojson"

BBOX = (20.85, 52.10, 21.27, 52.37)  # west, south, east, north (same as the frontend's WARSAW_BBOX)
OVERPASS = "https://overpass-api.de/api/interpreter"

CELL_M = 40          # grid resolution
SIGMA_M = 110        # kernel width: how far a venue's crowd "spills" into the street
PED_STEP_M = 25      # pedestrian streets are sampled every 25 m
MIN_AREA_M2 = 12000  # drop specks smaller than ~ a city block
MIN_HOLE_M2 = 9000

# weight ≈ how many people a thing puts on the street, relative to a café (1.0)
AMENITY_W = {
    "nightclub": 3.0, "biergarten": 2.5, "bar": 2.2, "pub": 2.2, "food_court": 1.5, "cinema": 2.0,
    "theatre": 2.0, "arts_centre": 1.5, "events_venue": 2.0, "marketplace": 2.0, "cafe": 1.0,
    "restaurant": 0.8, "ice_cream": 0.6, "community_centre": 0.6, "fast_food": 0.4,
}
MIX_LABEL = {
    "nightclub": "clubs", "bar": "bars & pubs", "pub": "bars & pubs", "biergarten": "bars & pubs",
    "cafe": "cafés", "restaurant": "restaurants", "fast_food": "restaurants", "food_court": "restaurants",
    "ice_cream": "cafés", "cinema": "cinemas & theatres", "theatre": "cinemas & theatres",
    "arts_centre": "culture", "events_venue": "culture", "community_centre": "culture",
    "marketplace": "markets", "square": "squares", "station": "stations", "attraction": "sights",
    "museum": "culture", "gallery": "culture", "dance": "clubs", "bowling_alley": "games",
    "escape_game": "games", "pedestrian": "pedestrian streets",
}


# ------------------------------------------------------------------------------------------------
# 1. data
# ------------------------------------------------------------------------------------------------

def overpass_query():
    w, s, e, n = BBOX
    bb = f"({s},{w},{n},{e})"
    amen = "|".join(AMENITY_W)
    return f"""[out:json][timeout:180];
(
  nwr["amenity"~"^({amen})$"]{bb};
  nwr["place"="square"]{bb};
  nwr["railway"="station"]{bb};
  nwr["station"="subway"]{bb};
  nwr["tourism"~"^(attraction|museum|gallery)$"]{bb};
  nwr["leisure"~"^(dance|bowling_alley|escape_game)$"]{bb};
)->.pois;
.pois out center tags;
way["highway"="pedestrian"]{bb}->.ped;
.ped out geom tags;
"""


def load_osm(refresh):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())
    print("downloading from Overpass (this takes ~30 s)…")
    body = urllib.parse.urlencode({"data": overpass_query()}).encode()
    req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": "syrenka.me busy-areas builder"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read())
    except urllib.error.URLError as e:
        # python.org builds on macOS ship without CA certs; fall back to the system bundle
        if not isinstance(e.reason, ssl.SSLCertVerificationError) or not Path("/etc/ssl/cert.pem").exists():
            raise
        ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
        with urllib.request.urlopen(req, timeout=240, context=ctx) as r:
            data = json.loads(r.read())
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(data))
    return data


def to_points(osm):
    """-> list of (lng, lat, weight, kind, name, street)"""
    pts = []
    for el in osm["elements"]:
        t = el.get("tags", {})
        if el["type"] == "way" and t.get("highway") == "pedestrian" and "geometry" in el:
            for lng, lat in sample_line([(g["lon"], g["lat"]) for g in el["geometry"]], PED_STEP_M):
                pts.append((lng, lat, 0.35, "pedestrian", None, t.get("name")))
            continue
        c = el.get("center") or ({"lat": el["lat"], "lon": el["lon"]} if "lat" in el else None)
        if not c:
            continue
        if t.get("amenity") in AMENITY_W:
            kind, w = t["amenity"], AMENITY_W[t["amenity"]]
        elif t.get("place") == "square":
            kind, w = "square", 3.0
        elif t.get("railway") == "station" or t.get("station") == "subway":
            kind, w = "station", 1.8
        elif t.get("tourism") in ("attraction", "museum", "gallery"):
            kind, w = t["tourism"], 0.7
        elif t.get("leisure") in ("dance", "bowling_alley", "escape_game"):
            kind, w = t["leisure"], {"dance": 2.0, "bowling_alley": 1.0, "escape_game": 0.8}[t["leisure"]]
        else:
            continue
        name = t.get("name") if kind == "square" else None
        pts.append((c["lon"], c["lat"], w, kind, name, t.get("addr:street")))
    return pts


# ------------------------------------------------------------------------------------------------
# geometry helpers (local metric projection around the city centre)
# ------------------------------------------------------------------------------------------------

LNG0, LAT0 = BBOX[0], BBOX[1]
MX = 111320 * math.cos(math.radians((BBOX[1] + BBOX[3]) / 2))
MY = 110540


def to_m(lng, lat):
    return (lng - LNG0) * MX, (lat - LAT0) * MY


def to_ll(x, y):
    return round(LNG0 + x / MX, 6), round(LAT0 + y / MY, 6)


def sample_line(coords, step):
    out = []
    for (a, b) in zip(coords, coords[1:]):
        ax, ay = to_m(*a)
        bx, by = to_m(*b)
        d = math.hypot(bx - ax, by - ay)
        n = max(1, int(d // step))
        for k in range(n):
            out.append(to_ll(ax + (bx - ax) * k / n, ay + (by - ay) * k / n))
    if coords:
        out.append(coords[-1])
    return out


def ring_area(r):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))) / 2


def point_in_ring(x, y, r):
    inside = False
    for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def simplify(r, tol):
    """Douglas-Peucker on a closed ring."""
    if len(r) < 8:
        return r

    def dp(pts):
        (ax, ay), (bx, by) = pts[0], pts[-1]
        L = math.hypot(bx - ax, by - ay) or 1e-9
        best, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            px, py = pts[i]
            d = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / L
            if d > best:
                best, idx = d, i
        if best > tol:
            return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])
        return [pts[0], pts[-1]]

    half = len(r) // 2
    return dp(r[: half + 1])[:-1] + dp(r[half:] + [r[0]])[:-1]


def chaikin(r, iterations=2):
    for _ in range(iterations):
        out = []
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        r = out
    return r


# ------------------------------------------------------------------------------------------------
# 2. density grid
# ------------------------------------------------------------------------------------------------

# Pedestrian ways and "attractions" only *boost* places that already have venues: on their own they
# light up park alleys, cemetery paths (Powązki) and graves tagged as sights, where nobody meets anyone.
BOOSTERS = {"pedestrian", "attraction"}


def social_density(pts):
    base, nx, ny = density_grid([p for p in pts if p[3] not in BOOSTERS])
    boost, _, _ = density_grid([p for p in pts if p[3] in BOOSTERS])
    return [[v + min(b, v) for v, b in zip(rv, rb)] for rv, rb in zip(base, boost)], nx, ny


def density_grid(pts):
    W, H = to_m(BBOX[2], BBOX[3])
    nx, ny = int(W // CELL_M) + 3, int(H // CELL_M) + 3  # +padding so every contour closes
    grid = [[0.0] * nx for _ in range(ny)]
    rad = int(3 * SIGMA_M // CELL_M)
    kernel = [[math.exp(-((dx * CELL_M) ** 2 + (dy * CELL_M) ** 2) / (2 * SIGMA_M ** 2)) for dx in range(-rad, rad + 1)] for dy in range(-rad, rad + 1)]
    for lng, lat, w, *_ in pts:
        x, y = to_m(lng, lat)
        cx, cy = int(round(x / CELL_M)) + 1, int(round(y / CELL_M)) + 1
        for ky, row in enumerate(kernel):
            gy = cy + ky - rad
            if 1 <= gy < ny - 1:
                g = grid[gy]
                for kx, kv in enumerate(row):
                    gx = cx + kx - rad
                    if 1 <= gx < nx - 1:
                        g[gx] += w * kv
    return grid, nx, ny


# ------------------------------------------------------------------------------------------------
# 3. marching squares -> rings (in metres)
# ------------------------------------------------------------------------------------------------

# corners: 8 = top-left (i,j), 4 = top-right (i,j+1), 2 = bottom-right (i+1,j+1), 1 = bottom-left (i+1,j)
# edges:   T = top, R = right, B = bottom, L = left
CASES = {
    1: [("L", "B")], 2: [("B", "R")], 3: [("L", "R")], 4: [("T", "R")], 6: [("T", "B")], 7: [("L", "T")],
    8: [("L", "T")], 9: [("T", "B")], 11: [("T", "R")], 12: [("L", "R")], 13: [("B", "R")], 14: [("L", "B")],
}


def contour_rings(grid, nx, ny, level):
    def edge_key(i, j, e):
        return {"T": ("h", i, j), "B": ("h", i + 1, j), "L": ("v", i, j), "R": ("v", i, j + 1)}[e]

    def edge_point(k):
        kind, i, j = k
        if kind == "h":
            a, b = grid[i][j], grid[i][j + 1]
            t = (level - a) / (b - a) if b != a else 0.5
            return ((j + t - 1) * CELL_M, (i - 1) * CELL_M)
        a, b = grid[i][j], grid[i + 1][j]
        t = (level - a) / (b - a) if b != a else 0.5
        return ((j - 1) * CELL_M, (i + t - 1) * CELL_M)

    adj = defaultdict(list)
    for i in range(ny - 1):
        gi, gi1 = grid[i], grid[i + 1]
        for j in range(nx - 1):
            tl, tr, br, bl = gi[j], gi[j + 1], gi1[j + 1], gi1[j]
            c = (8 if tl >= level else 0) | (4 if tr >= level else 0) | (2 if br >= level else 0) | (1 if bl >= level else 0)
            if c in (0, 15):
                continue
            if c in (5, 10):  # saddle: decide by the centre value
                hi = (tl + tr + br + bl) / 4 >= level
                segs = ([("L", "T"), ("B", "R")] if c == 5 else [("L", "B"), ("T", "R")]) if hi else \
                       ([("L", "B"), ("T", "R")] if c == 5 else [("L", "T"), ("B", "R")])
            else:
                segs = CASES[c]
            for a, b in segs:
                ka, kb = edge_key(i, j, a), edge_key(i, j, b)
                adj[ka].append(kb)
                adj[kb].append(ka)

    rings, seen = [], set()
    for start in list(adj):
        if start in seen:
            continue
        ring, prev, cur = [], None, start
        while True:
            seen.add(cur)
            ring.append(edge_point(cur))
            nxt = [k for k in adj[cur] if k != prev]
            if not nxt or nxt[0] == start:
                break
            prev, cur = cur, nxt[0]
            if cur in seen:
                break
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def polygons(rings, min_area, min_hole):
    """Split rings into outer rings with their holes (a ring inside an odd number of rings is a hole)."""
    rings = [r for r in rings if ring_area(r) >= min(min_area, min_hole)]
    depth = [sum(point_in_ring(*r[0], o) for o in rings if o is not r) for r in rings]
    outers = [r for r, d in zip(rings, depth) if d % 2 == 0 and ring_area(r) >= min_area]
    polys = []
    for o in outers:
        holes = [r for r, d in zip(rings, depth) if d % 2 == 1 and ring_area(r) >= min_hole and point_in_ring(*r[0], o)
                 and not any(point_in_ring(*r[0], o2) for o2 in outers if o2 is not o and ring_area(o2) < ring_area(o) and point_in_ring(*o2[0], o))]
        polys.append((o, holes))
    return polys


def finish_ring(r):
    r = chaikin(simplify(r, 7), 2)
    ll = [to_ll(x, y) for x, y in r]
    return ll + [ll[0]]


# ------------------------------------------------------------------------------------------------
# 4. naming and description
# ------------------------------------------------------------------------------------------------

def nice(street):
    """Everyday names for long official ones (all the Vistula boulevards are just 'Bulwary Wiślane')."""
    if street.startswith("Bulwar"):
        return "Bulwary Wiślane"
    return street


def describe(outer, holes, pts_m):
    inside = [p for p in pts_m if point_in_ring(p[0], p[1], outer) and not any(point_in_ring(p[0], p[1], h) for h in holes)]
    score = sum(p[2] for p in inside)
    venues = [p for p in inside if p[3] != "pedestrian"]
    streets = Counter(nice(p[6]) for p in inside if p[6] and p[3] != "pedestrian")
    for p in inside:  # pedestrian streets and real squares name an area better than one bar's address
        if p[3] == "pedestrian" and p[6]:
            streets[nice(p[6])] += 0.6
        if p[3] == "square" and p[5]:
            streets[nice(p[5])] += 1 if p[5].startswith("Skwer") else 6  # a "skwer" is a small green, not a plaza
    top = [s for s, _ in streets.most_common(2)]
    name = " / ".join(top) if top else "Busy area"
    mix = Counter(MIX_LABEL.get(p[3], p[3]) for p in inside)
    if "pedestrian streets" in mix:
        mix["pedestrian streets"] = len({p[6] for p in inside if p[3] == "pedestrian" and p[6]}) or 1
    return name, round(score, 1), len(venues), dict(mix.most_common(5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download from Overpass")
    # ~top 2% / top 0.5% of the city's social density; lower merges the whole centre into one blob
    ap.add_argument("--busy", type=float, default=18.0, help="density threshold for the area outline")
    ap.add_argument("--very", type=float, default=45.0, help="density threshold for the very busy core")
    ap.add_argument("--stats", action="store_true", help="print the density distribution and exit")
    a = ap.parse_args()

    osm = load_osm(a.refresh)
    pts = to_points(osm)
    print(f"{len(pts)} weighted points from {len(osm['elements'])} OSM elements")
    grid, nx, ny = social_density(pts)
    if a.stats:
        vals = sorted(v for row in grid for v in row if v > 0.5)
        for q in (0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999):
            print(f"p{q * 100:g}: {vals[int(q * (len(vals) - 1))]:.1f}")
        return

    pts_m = [(*to_m(lng, lat), w, kind, None, name, street) for lng, lat, w, kind, name, street in pts]
    features = []
    areas = polygons(contour_rings(grid, nx, ny, a.busy), MIN_AREA_M2, MIN_HOLE_M2)
    cores = polygons(contour_rings(grid, nx, ny, a.very), MIN_AREA_M2 / 3, MIN_HOLE_M2)
    areas.sort(key=lambda oh: -describe(*oh, pts_m)[1])
    for n, (outer, holes) in enumerate(areas, 1):
        name, score, venues, mix = describe(outer, holes, pts_m)
        area_id = f"busy-{n:02d}"
        km2 = (ring_area(outer) - sum(ring_area(h) for h in holes)) / 1e6
        why = ", ".join(f"{v} {k}" for k, v in mix.items())
        my_cores = [c for c in cores if point_in_ring(*c[0][0], outer)]
        features.append({"type": "Feature", "id": area_id, "properties": {
            "id": area_id, "name": name, "level": "busy", "score": score, "venues": venues, "area_km2": round(km2, 3),
            "mix": mix, "why": f"{why} in {km2:.2f} km²"},
            "geometry": {"type": "Polygon", "coordinates": [finish_ring(outer)] + [finish_ring(h) for h in holes]}})
        for k, (core, choles) in enumerate(my_cores):
            cname, cscore, cvenues, cmix = describe(core, choles, pts_m)
            features.append({"type": "Feature", "id": f"{area_id}-core{k + 1}", "properties": {
                "id": f"{area_id}-core{k + 1}", "parent": area_id, "name": cname, "level": "very_busy", "score": cscore,
                "venues": cvenues, "area_km2": round((ring_area(core) - sum(ring_area(h) for h in choles)) / 1e6, 3), "mix": cmix},
                "geometry": {"type": "Polygon", "coordinates": [finish_ring(core)] + [finish_ring(h) for h in choles]}})

    fc = {"type": "FeatureCollection", "properties": {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": f"Gaussian density (σ={SIGMA_M} m, {CELL_M} m grid) of weighted OSM social venues, squares, "
                  f"pedestrian streets and stations; outlines at busy≥{a.busy}, very_busy≥{a.very}",
        "source": "© OpenStreetMap contributors (ODbL), via Overpass API"}, "features": features}
    text = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(text)
    MOCK_OUT.parent.mkdir(parents=True, exist_ok=True)
    MOCK_OUT.write_text(text)
    busy = [f for f in features if f["properties"]["level"] == "busy"]
    print(f"{len(busy)} busy areas, {len(features) - len(busy)} very busy cores -> {OUT.relative_to(ROOT)} ({len(text) // 1024} KB)")
    for f in busy:
        p = f["properties"]
        print(f"  {p['id']}  {p['name'][:36]:36s}  score {p['score']:7.1f}  {p['area_km2']:.2f} km²  {p['why'][:60]}")


if __name__ == "__main__":
    main()
