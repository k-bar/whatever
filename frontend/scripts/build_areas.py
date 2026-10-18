"""Builds public/warsaw_areas.geojson: outlines of Warsaw's districts and neighbourhoods.

Search uses them to find what's *in* an area by location (many venues have no district field), and the
map draws the searched area with a dashed line. Source: OpenStreetMap (© OpenStreetMap contributors,
ODbL) via the Overpass API:
  admin_level 9  -> the 18 dzielnice (kind "district")
  admin_level 10 -> MSI areas, e.g. Saska Kępa, Powiśle, Stare Miasto (kind "area")
  admin_level 11 -> smaller named areas not already at level 10, e.g. Muranów, Kabaty (kind "area")

Run from frontend/:  python3 scripts/build_areas.py   (needs shapely and httpx)
"""

import json
import sys
from pathlib import Path

from shapely.geometry import LineString, mapping, shape
from shapely.ops import polygonize, unary_union

OUT = Path(__file__).resolve().parent.parent / "public" / "warsaw_areas.geojson"
QUERY = """[out:json][timeout:180];
area["name"="Warszawa"]["admin_level"="6"]->.w;
relation(area.w)["boundary"="administrative"]["admin_level"~"^(9|10|11)$"];
out geom;"""
TOLERANCE = 0.00012  # ~10 m; keeps the outline faithful and the file small


def fetch():
    import httpx  # bundles certificates (python.org builds on macOS have none by default)

    r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": QUERY}, timeout=240,
                   headers={"User-Agent": "syrenka-areas-build/1.0", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()["elements"]


def polygon_of(rel):
    lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
             for m in rel.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
    polys = list(polygonize(unary_union(lines)))
    return unary_union(polys) if polys else None


def main():
    rels = fetch()
    level10 = {r["tags"].get("name") for r in rels if r["tags"].get("admin_level") == "10"}
    features = []
    for r in sorted(rels, key=lambda r: (r["tags"].get("admin_level"), r["tags"].get("name", ""))):
        tags = r["tags"]
        name, level = tags.get("name"), tags.get("admin_level")
        if not name or (level == "11" and name in level10):
            continue
        geom = polygon_of(r)
        if geom is None or geom.is_empty:
            print("skip (no polygon):", name, file=sys.stderr)
            continue
        geom = geom.simplify(TOLERANCE, preserve_topology=True)
        gj = json.loads(json.dumps(mapping(geom)), parse_float=lambda s: round(float(s), 5))
        features.append({"type": "Feature", "properties": {"name": name, "kind": "district" if level == "9" else "area", "level": int(level), "osm_id": r["id"]}, "geometry": gj})
    # each area gets the district it lies in, so "Saska Kępa" can say "Praga-Południe"
    districts = [(f["properties"]["name"], shape(f["geometry"])) for f in features if f["properties"]["kind"] == "district"]
    for f in features:
        if f["properties"]["kind"] == "area":
            c = shape(f["geometry"]).representative_point()
            f["properties"]["district"] = next((n for n, g in districts if g.contains(c)), None)
    fc = {"type": "FeatureCollection", "attribution": "© OpenStreetMap contributors (ODbL)", "features": features}
    OUT.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(features)} areas -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
