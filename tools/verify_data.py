#!/usr/bin/env python3
"""Acceptance checks for the published data (spec §12 "データ").

1. Draw random parcels from the city shapefile and confirm that the served
   PMTiles return the same lot number and place name at that spot.
2. Measure how far the converted city parcels sit from the MOJ map.
3. With --gsi, estimate the offset between the city parcels and the GSI
   basemap: shift the parcel lines on a grid and find where they cut
   through GSI building footprints the least. Fetches a handful of GSI
   vector tiles (experimental_bvmap, z16).

Usage: work/.venv/bin/python tools/verify_data.py [--samples 20] [--seed N] [--gsi]
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyogrio
import shapely
import shapely.affinity
import shapely.geometry
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent))
import build_data as b  # noqa: E402

DECODE = "tippecanoe-decode"


def tile_of(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def decode(path, z, x, y):
    out = subprocess.run([DECODE, str(path), str(z), str(x), str(y)], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    layers = {}
    for fc in json.loads(out.stdout)["features"]:
        layers[fc["properties"]["layer"]] = fc["features"]
    return layers


def part_of(lat):
    edges = json.loads(b.SPLIT_FILE.read_text())
    return b.PARTS - 1 - int(np.searchsorted(edges, lat))


def check_lots(samples, seed, year):
    meta, fids, wkb, fields = pyogrio.raw.read(b.CITY_POLY, encoding="cp932")
    col = dict(zip(meta["fields"], fields))
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(wkb), size=samples, replace=False)
    geoms = b.to_wgs84(b.valid(shapely.from_wkb(wkb[picks])), b.CITY_CRS)
    ok = 0
    print(f"{'OBJEXOID':>9}  {'source 地番':<12} {'tile 地番':<12} 所在（source → tile）")
    for g, i in zip(geoms, picks):
        p = shapely.point_on_surface(g)
        part = part_of(p.y)
        x, y = tile_of(p.x, p.y, 17)
        layers = decode(b.ROOT / f"chiban_fukuyama_{year}_{part}.pmtiles", 17, x, y)
        hit = None
        for f in layers.get("chiban", []):
            if f["geometry"]["type"] in ("Polygon", "MultiPolygon") and shapely.from_geojson(json.dumps(f["geometry"])).buffer(1e-7).contains(p):
                hit = f
                if f.get("id") == int(col["OBJEXOID"][i]):
                    break
        src = (col["TXTCD"][i], b.fix_gaiji(col["KOAZA_小字"][i]))
        got = (hit["properties"].get("chiban"), hit["properties"].get("shozai")) if hit else (None, None)
        same = src == got
        ok += same
        print(f"{col['OBJEXOID'][i]:>9}  {src[0]:<12} {str(got[0]):<12} {src[1]} → {got[1]}  {'OK' if same else 'NG'}")
    print(f"lot check: {ok}/{samples} match")
    return ok == samples


def check_offsets():
    to_m = Transformer.from_crs("EPSG:4326", b.CITY_CRS, always_xy=True)
    meta, fids, wkb, fields = pyogrio.raw.read(b.CITY_POLY, encoding="cp932", columns=["TXTCD"])
    city = b.valid(shapely.from_wkb(wkb))
    chiban = fields[0]

    # MOJ parcels (public-coordinate sheets) with the same lot number that
    # overlap a city parcel: compare representative points.
    meta, fids, mwkb, mf = pyogrio.raw.read(b.MOJ_FGB, columns=["地番", "座標値種別"])
    moj = shapely.from_wkb(mwkb)
    moj = shapely.transform(moj, lambda xy: np.column_stack(to_m.transform(xy[:, 0], xy[:, 1])))
    moj = b.valid(moj)
    tree = shapely.STRtree(city)
    reps = shapely.point_on_surface(moj)
    mi, ci = tree.query(reps, predicate="within")
    same = np.array([mf[0][m] == chiban[c] for m, c in zip(mi, ci)], dtype=bool)
    mi, ci = mi[same], ci[same]
    d = shapely.distance(shapely.centroid(moj[mi]), shapely.centroid(city[ci]))
    print(f"MOJ vs city centroid offset (same lot, n={len(d)}): median {np.median(d):.2f} m, p90 {np.percentile(d, 90):.2f} m, p99 {np.percentile(d, 99):.2f} m")
    surveyed = np.array([mf[1][m] == "測量成果" for m in mi])
    if surveyed.any():
        ds = d[surveyed]
        print(f"  only MOJ sheets marked 測量成果 (n={len(ds)}): median {np.median(ds):.2f} m, p90 {np.percentile(ds, 90):.2f} m")
    return float(np.median(d))


GSI_POINTS = {  # town centres across the city, one z16 tile each
    "福山駅": (133.3620, 34.4890),
    "神辺": (133.3850, 34.5420),
    "新市": (133.2680, 34.5530),
    "松永": (133.2560, 34.4480),
    "鞆": (133.3830, 34.3840),
    "駅家": (133.3280, 34.5530),
}


def check_gsi():
    import urllib.request

    import mapbox_vector_tile

    to_m = Transformer.from_crs("EPSG:4326", b.CITY_CRS, always_xy=True)
    results = []
    for name, (lon, lat) in GSI_POINTS.items():
        x, y = tile_of(lon, lat, 16)
        url = f"https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/16/{x}/{y}.pbf"
        data = urllib.request.urlopen(url, timeout=30).read()
        tile = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})
        layer = tile.get("building")
        if not layer:
            continue
        ext = layer.get("extent", 4096)

        def to_lonlat(px, py):
            n = 2 ** 16
            lon = (x + px / ext) / n * 360 - 180
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / ext) / n))))
            return lon, lat

        polys = []
        for f in layer["features"]:
            g = shapely.geometry.shape(f["geometry"])
            g = shapely.transform(g, lambda xy: np.array([to_m.transform(*to_lonlat(px, py)) for px, py in xy]))
            polys.append(g)
        bld = shapely.make_valid(shapely.union_all(np.array(polys, dtype=object)))
        inner = shapely.buffer(bld, -0.3)
        x0, y0, x1, y1 = bld.bounds
        bbox = shapely.box(x0, y0, x1, y1)
        meta, fids, wkb, fields = pyogrio.raw.read(b.CITY_POLY, bbox=(x0, y0, x1, y1), columns=[])
        lines = shapely.intersection(shapely.union_all(shapely.boundary(b.valid(shapely.from_wkb(wkb)))), bbox)

        def cut(dx, dy):
            return shapely.length(shapely.intersection(shapely.affinity.translate(lines, dx, dy), inner))

        best = min(((cut(dx, dy), dx, dy) for dx in range(-6, 7) for dy in range(-6, 7)))
        _, bx, by = best
        fine = min(((cut(bx + dx / 2, by + dy / 2), bx + dx / 2, by + dy / 2) for dx in range(-2, 3) for dy in range(-2, 3)))
        base = cut(0, 0)
        if base < 50:
            print(f"GSI {name} 16/{x}/{y}: too few buildings across parcel lines to judge")
            continue
        results.append(math.hypot(fine[1], fine[2]))
        print(f"GSI {name} 16/{x}/{y}: {len(polys)} buildings, best shift ({fine[1]:+.1f} m, {fine[2]:+.1f} m), "
              f"crossing length {base:.0f} m at 0 → {fine[0]:.0f} m at best")
    if results:
        print(f"GSI offset: max {max(results):.1f} m over {len(results)} tiles")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--year", default="2026")
    ap.add_argument("--gsi", action="store_true")
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else int.from_bytes(np.random.bytes(4), "little")
    print(f"seed {seed}")
    good = check_lots(a.samples, seed, a.year)
    check_offsets()
    if a.gsi:
        check_gsi()
    sys.exit(0 if good else 1)
