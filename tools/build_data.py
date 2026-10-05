#!/usr/bin/env python3
"""Build the static data files served next to index.html.

Inputs live in work/raw/ (never committed). Outputs:
  work/mid/*.geojsonl            intermediate GeoJSON sequences for tippecanoe
  fukuyama_mask.geojson          world-minus-Fukuyama mask polygon (F10)
  search.json, search/*.json     lot-number search index (F7)
  work/mid/bounds.json           city bbox used for maxBounds

Run tools/build.sh instead of calling this directly; it also runs tippecanoe.
"""
import csv
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "work" / "raw"
MID = ROOT / "work" / "mid"

CITY_POLY = RAW / "地番図" / "面" / "筆界_面.shp"
CITY_LABEL = RAW / "地番図" / "線" / "地番_線.shp"
MOJ_FGB = MID / "houmukyoku_raw.fgb"
CENSUS_TOPO = RAW / "r2ka34207.topojson"
ADMIN_N03 = RAW / "N03_34" / "N03-20260101_34.shp"
MASTER = RAW / "mt_parcel_city342076.csv"
MASTER_POS = RAW / "mt_parcel_pos_city342076.csv"

# The city shapefile ships without a .prj. Its coordinates fall in
# Japan Plane Rectangular CS zone III, and 98% of the address-registry
# representative points land inside the same-named parcel under JGD2011.
CITY_CRS = "EPSG:6671"

COORD_DIGITS = 7  # ~1 cm

# One PMTiles file per source would exceed GitHub's 100 MB push limit, so
# each source is cut into latitude bands with equal parcel counts.
PARTS = 3
SPLIT_FILE = MID / "split.json"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fix_gaiji(s):
    # The city's place names carry vendor gaiji in the Private Use Area with
    # no published mapping (the MOJ map has no koaza there to compare), so
    # show the conventional geta mark rather than guess a character.
    if not s:
        return s
    return re.sub("[\ue000-\uf8ff]", "〓", s)


def to_wgs84(geoms, src_crs):
    tr = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
    return shapely.transform(geoms, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))


def tile_edge_lat(lat, z=15):
    n = 2 ** z
    y = round((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def make_split(lats):
    # Snap band edges to z15 tile rows so few tiles exist in two files.
    qs = np.nanquantile(lats, [k / PARTS for k in range(1, PARTS)])
    edges = [tile_edge_lat(q) for q in qs]
    SPLIT_FILE.write_text(json.dumps(edges))
    log(f"  split latitudes {edges}")


def write_parts(stem, items):
    """items yields (lat, feature); writes stem.<k>.geojsonl per band."""
    edges = json.loads(SPLIT_FILE.read_text())
    files = [open(MID / f"{stem}.{k}.geojsonl", "w", encoding="utf-8") for k in range(PARTS)]
    counts = [0] * PARTS
    for lat, feat in items:
        k = PARTS - 1 - int(np.searchsorted(edges, lat))  # part 0 = north
        files[k].write(json.dumps(feat, ensure_ascii=False, separators=(",", ":")))
        files[k].write("\n")
        counts[k] += 1
    for f in files:
        f.close()
    log(f"  wrote work/mid/{stem}.*.geojsonl {counts}")


def rounded(geoms):
    # set_precision snaps vertices to a 1e-7 degree grid and repairs any
    # collapse it causes, so the tiles never carry spurious precision.
    return shapely.set_precision(geoms, 10 ** -COORD_DIGITS, mode="valid_output")


def valid(geoms):
    bad = ~shapely.is_valid(geoms)
    if bad.any():
        log(f"  repairing {bad.sum()} invalid geometries")
        geoms = geoms.copy()
        geoms[bad] = shapely.make_valid(geoms[bad])
        # make_valid may return collections; keep the polygonal part only.
        for i in np.flatnonzero(bad):
            g = geoms[i]
            if g.geom_type == "GeometryCollection":
                polys = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
                geoms[i] = shapely.union_all(polys) if polys else shapely.Polygon()
    return geoms


def readable_angle(deg):
    """Map-plane bearing of the label baseline -> MapLibre text-rotate.

    MapLibre rotates clockwise; keep text upright (-90, 90].
    """
    r = -deg
    while r > 90:
        r -= 180
    while r <= -90:
        r += 180
    return round(r, 1)


def point_xy(points):
    # shapely.get_coordinates drops empty geometries and get_x raises on
    # them, either of which would misalign rows with their attributes.
    out = np.full((len(points), 2), np.nan)
    ok = ~(shapely.is_missing(points) | shapely.is_empty(points))
    out[ok, 0] = shapely.get_x(points[ok])
    out[ok, 1] = shapely.get_y(points[ok])
    return out


def shared_edges(geoms, scale, cell):
    """Outline linework with each shared parcel edge kept once.

    Both sources are topologically clean (neighbours share identical
    vertices), so exact segment de-duplication halves the vertex count.
    Used for z15, where nothing is clickable and only lines are drawn.
    `scale` quantises coordinates to integers before matching; `cell` is the
    merge-grid size in source units.
    """
    coords, idx = shapely.get_coordinates(shapely.boundary(geoms), return_index=True)
    q = np.round(coords * scale).astype(np.int64)
    same = idx[1:] == idx[:-1]
    a, b = q[:-1][same], q[1:][same]
    swap = (a[:, 0] > b[:, 0]) | ((a[:, 0] == b[:, 0]) & (a[:, 1] > b[:, 1]))
    segs = np.where(swap[:, None], np.hstack([b, a]), np.hstack([a, b]))
    segs = np.unique(segs[~((segs[:, 0] == segs[:, 2]) & (segs[:, 1] == segs[:, 3]))], axis=0)
    # line_merge over millions of segments at once is slow; merge per cell.
    size = 2 * cell * scale  # segs hold endpoint sums, i.e. twice the midpoint
    cell = ((segs[:, 0] + segs[:, 2]) // size) * 100000 + (segs[:, 1] + segs[:, 3]) // size
    order = np.argsort(cell, kind="stable")
    segs, cell = segs[order], cell[order]
    out = []
    for chunk in np.split(segs, np.flatnonzero(np.diff(cell)) + 1):
        merged = shapely.line_merge(shapely.multilinestrings(shapely.linestrings(chunk.reshape(-1, 2, 2) / scale)))
        out.extend(getattr(merged, "geoms", [merged]))
    return np.array(out, dtype=object)


def edge_features(lines):
    lats = point_xy(shapely.get_point(lines, 0))[:, 1]
    for g, lat in zip(lines, lats):
        yield lat, {
            "type": "Feature",
            "properties": {},
            "tippecanoe": {"maxzoom": 15},
            "geometry": json.loads(shapely.to_geojson(g)),
        }


def chiban_ok(c):
    return bool(c) and c != "-"


# ---------------------------------------------------------------- city

def build_city():
    log("city: reading parcels")
    meta, fids, wkb, fields = pyogrio.raw.read(CITY_POLY, encoding="cp932")
    col = dict(zip(meta["fields"], fields))
    geoms = valid(shapely.from_wkb(wkb))
    edges = shared_edges(geoms, 100, 1000)
    geoms = rounded(to_wgs84(geoms, CITY_CRS))
    rc = point_xy(shapely.point_on_surface(geoms))
    make_split(rc[:, 1])
    log("city: de-duplicating shared edges for z15")
    write_parts("chiban_city_edges", edge_features(rounded(to_wgs84(edges, CITY_CRS))))
    ids = col["OBJEXOID"]
    chiban = col["TXTCD"]
    shozai = [fix_gaiji(s) for s in col["KOAZA_小字"]]

    def feats():
        for i in range(len(geoms)):
            g = geoms[i]
            if g.is_empty:
                continue
            yield rc[i, 1], {
                "type": "Feature",
                "id": int(ids[i]),
                "properties": {"chiban": chiban[i] or "", "shozai": shozai[i] or ""},
                "tippecanoe": {"minzoom": 16},
                "geometry": json.loads(shapely.to_geojson(g)),
            }

    write_parts("chiban_city", feats())

    log("city: reading label baselines")
    meta, fids, wkb, fields = pyogrio.raw.read(CITY_LABEL, encoding="cp932")
    col = dict(zip(meta["fields"], fields))
    lines = shapely.from_wkb(wkb)
    a = point_xy(shapely.get_point(lines, 0))
    b = point_xy(shapely.get_point(lines, -1))
    d = b - a
    angles = np.degrees(np.arctan2(d[:, 1], d[:, 0]))
    mids = shapely.points((a + b) / 2)
    mids = rounded(to_wgs84(mids, CITY_CRS))
    lab_chiban = col["TXTCD"]

    def labels():
        for i in range(len(mids)):
            c = lab_chiban[i]
            if not chiban_ok(c) or np.isnan(a[i, 0]):
                continue
            p = shapely.get_coordinates(mids[i])[0]
            yield p[1], {
                "type": "Feature",
                "properties": {"chiban": c, "rot": readable_angle(angles[i])},
                "tippecanoe": {"minzoom": 17},
                "geometry": {"type": "Point", "coordinates": [round(p[0], COORD_DIGITS), round(p[1], COORD_DIGITS)]},
            }

    write_parts("chiban_city_label", labels())

    # Representative points for the search index (city parcels may be
    # missing from the address registry's position file).
    out = MID / "city_points.tsv"
    with open(out, "w", encoding="utf-8") as f:
        for i in range(len(geoms)):
            if geoms[i].is_empty or not chiban_ok(chiban[i]):
                continue
            f.write(f"{shozai[i] or ''}\t{chiban[i]}\t{rc[i][0]:.6f}\t{rc[i][1]:.6f}\n")
    log(f"  wrote {out.relative_to(ROOT)}")


# ---------------------------------------------------------------- MOJ

def build_moj():
    log("moj: reading converted map XML")
    meta, fids, wkb, fields = pyogrio.raw.read(MOJ_FGB)
    col = dict(zip(meta["fields"], fields))
    geoms = valid(shapely.from_wkb(wkb))
    log("moj: de-duplicating shared edges for z15")
    write_parts("houmukyoku_edges", edge_features(rounded(shared_edges(geoms, 10 ** COORD_DIGITS, 0.01))))
    geoms = rounded(geoms)
    reps = point_xy(shapely.point_on_surface(geoms))

    def s(name, i):
        v = col[name][i]
        return v if v else ""

    def feats():
        for i in range(len(geoms)):
            g = geoms[i]
            if g.is_empty:
                continue
            yield reps[i, 1], {
                "type": "Feature",
                "id": i + 1,
                "tippecanoe": {"minzoom": 16},
                "properties": {
                    "chiban": s("地番", i),
                    "oaza": s("大字名", i),
                    "chome": s("丁目名", i),
                    "koaza": s("小字名", i),
                    "zumei": s("地図名", i),
                },
                "geometry": json.loads(shapely.to_geojson(g)),
            }

    write_parts("houmukyoku", feats())

    def labels():
        for i in range(len(geoms)):
            c = s("地番", i)
            if geoms[i].is_empty or not chiban_ok(c):
                continue
            yield reps[i, 1], {
                "type": "Feature",
                "properties": {"chiban": c},
                "tippecanoe": {"minzoom": 17},
                "geometry": {"type": "Point", "coordinates": [round(reps[i][0], COORD_DIGITS), round(reps[i][1], COORD_DIGITS)]},
            }

    write_parts("houmukyoku_label", labels())


# ---------------------------------------------------------------- mask

def topojson_polygons(path):
    topo = json.loads(path.read_text(encoding="utf-8"))
    tf = topo.get("transform")
    arcs = []
    for arc in topo["arcs"]:
        if tf:
            a = np.cumsum(np.array(arc, dtype=float), axis=0)
            a = a * tf["scale"] + tf["translate"]
        else:
            a = np.array(arc, dtype=float)
        arcs.append(a)

    def ring(idx):
        pts = []
        for k in idx:
            a = arcs[k] if k >= 0 else arcs[~k][::-1]
            pts.extend(a[1:] if pts else a)
        return pts

    out = []
    for obj in topo["objects"].values():
        for g in obj["geometries"]:
            if g["type"] == "Polygon":
                out.append(shapely.Polygon(ring(g["arcs"][0]), [ring(r) for r in g["arcs"][1:]]))
            elif g["type"] == "MultiPolygon":
                out.append(shapely.MultiPolygon([(ring(p[0]), [ring(r) for r in p[1:]]) for p in g["arcs"]]))
    return out


def build_mask():
    log("mask: dissolving census blocks")
    polys = shapely.make_valid(np.array(topojson_polygons(CENSUS_TOPO), dtype=object))
    outline = shapely.union_all(polys)
    # The census blocks leave out uninhabited islets (弁天島, 皇后島, ...);
    # the MLIT administrative area has every one of them.
    meta, fids, wkb, fields = pyogrio.raw.read(ADMIN_N03, where="N03_007 = '34207'")
    admin = shapely.union_all(shapely.make_valid(shapely.from_wkb(wkb)))
    # Work in metres for buffering.
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:6671", always_xy=True)
    to_deg = Transformer.from_crs("EPSG:6671", "EPSG:4326", always_xy=True)
    fwd = lambda g: shapely.transform(g, lambda xy: np.column_stack(to_m.transform(xy[:, 0], xy[:, 1])))
    inv = lambda g: shapely.transform(g, lambda xy: np.column_stack(to_deg.transform(xy[:, 0], xy[:, 1])))
    outline_m = shapely.union(shapely.buffer(fwd(outline), 30), shapely.buffer(fwd(admin), 20))

    # Reclaimed land and port facilities may postdate the 2020 census
    # boundary. Grow the outline to cover every city / MOJ parcel instead
    # of clipping real parcels away.
    log("mask: checking parcels outside the outline")
    extra = []
    for name, path, crs in (("city", CITY_POLY, CITY_CRS), ("moj", MOJ_FGB, "EPSG:4326")):
        meta, fids, wkb, fields = pyogrio.raw.read(path, columns=[])
        g = shapely.from_wkb(wkb)
        g = g if crs == CITY_CRS else fwd(g)
        g = shapely.make_valid(g)
        shapely.prepare(outline_m)
        out = ~shapely.within(g, outline_m)
        log(f"  {name}: {out.sum()} of {len(g)} parcels extend beyond the outline")
        if out.any():
            extra.append(shapely.union_all(shapely.buffer(g[out], 5)))
    grown = shapely.union_all([outline_m, *extra])
    # Drop slivers, keep islets; close pinholes inside the city.
    parts = [p for p in getattr(grown, "geoms", [grown]) if p.area > 100]
    parts = [shapely.Polygon(p.exterior, [r for r in p.interiors if shapely.Polygon(r).area > 1e6]) for p in parts]
    city_m = shapely.MultiPolygon(parts)
    city_m = shapely.simplify(city_m, 15, preserve_topology=True)
    city = inv(city_m)
    log(f"  outline parts: {len(parts)} (islands included)")

    world = shapely.box(-180, -85, 180, 85)
    mask = shapely.set_precision(shapely.difference(world, city), 1e-5)
    (ROOT / "fukuyama_mask.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": json.loads(shapely.to_geojson(mask))}]},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    b = city.bounds
    (MID / "bounds.json").write_text(json.dumps({"bbox": [round(v, 5) for v in b]}))
    (MID / "outline.geojson").write_text(shapely.to_geojson(city))
    log(f"  wrote fukuyama_mask.geojson ({(ROOT / 'fukuyama_mask.geojson').stat().st_size // 1024} KB), bbox {b}")


# ---------------------------------------------------------------- search

def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s+", "", s)
    return s.replace("ー", "-").replace("−", "-").replace("‐", "-").replace("－", "-")


def build_search():
    log("search: joining address registry")
    names = {}
    for r in csv.DictReader(open(MASTER, encoding="utf-8")):
        if r["ablt_date"]:
            continue  # abolished lots
        key = (r["machiaza_id"], r["prc_id"])
        chiban = "-".join(x for x in (r["prc_num1"], r["prc_num2"], r["prc_num3"]) if x)
        names[key] = (r["oaza_cho"] + r["chome"], chiban)

    towns = {}  # town name -> {chiban: (lon, lat)}
    for r in csv.DictReader(open(MASTER_POS, encoding="utf-8")):
        key = (r["machiaza_id"], r["prc_id"])
        if key not in names or not r["rep_lon"]:
            continue
        town, chiban = names[key]
        towns.setdefault(town, {})[chiban] = (float(r["rep_lon"]), float(r["rep_lat"]))
    from_master = sum(len(v) for v in towns.values())
    all_towns = sorted({t for t, _ in names.values()}, key=len, reverse=True)
    # The registry and the city spell some towns differently
    # (加茂町字中野 vs 加茂町大字中野字…), so fall back to a 大字/字-free match.
    bare = lambda t: t.replace("大字", "").replace("字", "")
    bare_towns = sorted(((bare(t), t) for t in all_towns), key=lambda bt: len(bt[0]), reverse=True)

    # City parcels: map "大字…字…" to the longest registry town prefix.
    log("search: adding city parcels missing from the registry")
    added = 0
    unmatched = defaultdict(int)
    for line in open(MID / "city_points.tsv", encoding="utf-8"):
        shozai, chiban, lon, lat = line.rstrip("\n").split("\t")
        town = next((t for t in all_towns if shozai.startswith(t)), None)
        if town is None:
            b = bare(shozai)
            town = next((t for bt, t in bare_towns if b.startswith(bt)), None)
        if town is None:
            unmatched[shozai] += 1
            continue
        d = towns.setdefault(town, {})
        if chiban not in d:
            d[chiban] = (float(lon), float(lat))
            added += 1
    log(f"  registry {from_master}, city-only {added}, unmatched city names {len(unmatched)} ({sum(unmatched.values())} parcels)")

    # Write: search.json = town list; search/<n>.json = lots of one town.
    out_dir = ROOT / "search"
    out_dir.mkdir(exist_ok=True)
    for p in out_dir.glob("*.json"):
        p.unlink()
    index = []
    for n, town in enumerate(sorted(towns)):
        lots = towns[town]
        lons = [v[0] for v in lots.values()]
        lats = [v[1] for v in lots.values()]
        index.append({"n": town, "k": norm(town), "f": n, "c": len(lots),
                      "b": [round(min(lons), 5), round(min(lats), 5), round(max(lons), 5), round(max(lats), 5)]})
        # Compact: [chiban, lon*1e6, lat*1e6] with integer micro-degrees.
        rows = [[c, round(v[0] * 1e6), round(v[1] * 1e6)] for c, v in sorted(lots.items(), key=lambda kv: natural_key(kv[0]))]
        (out_dir / f"{n}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(p.stat().st_size for p in out_dir.glob("*.json"))
    log(f"  wrote search.json ({len(index)} towns, {(ROOT / 'search.json').stat().st_size // 1024} KB) and search/ ({total // 1024} KB)")


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


if __name__ == "__main__":
    steps = {"city": build_city, "moj": build_moj, "mask": build_mask, "search": build_search}
    for name in sys.argv[1:] or ["city", "moj", "mask", "search"]:
        steps[name]()
