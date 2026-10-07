# 福山市 地番マップ (Fukuyama lot-number map)

A static web map that overlays the lot boundaries and lot numbers (地番) of
Fukuyama City, Hiroshima, on GSI aerial photos or base maps. It is a single
`index.html` plus PMTiles vector tiles; there is no server-side code.

The lines are **not survey results**. Do not use this map to settle
boundaries, measure distances or areas, or confirm rights.

## Features

- Background: GSI seamless aerial photo / pale map / standard map, with
  brightness and contrast for the photo
- Two lot layers that can be shown together or alone, each with its own
  line opacity:
  - 地番図（市） — Fukuyama City's tax-assessment lot map (solid line)
  - 法務局地図 — MOJ registry map, public-coordinate sheets only (dashed)
- Lot labels from zoom 17
- Optional road layer: national and prefectural road centre lines in their own
  colours (from zoom 11) and road edges (from zoom 16), from GSI optimised
  vector tiles, with its own line width and opacity. It shows the mapped
  roads, not the legal road area (道路区域)
- Click / tap a lot (zoom 16+) to see its lot number, location and source.
  With the road layer on, it also says whether a national / prefectural road
  centre line runs through the lot, or how far the nearest one is (within
  30 m, with GSI's width class). Only loaded tiles count, so parts of the lot
  off screen are left out
- Lot search by town + lot number (e.g. `青葉台一丁目 4-1`), entirely
  client-side
- Current location (browser geolocation, never sent anywhere)
- Shareable URL hash: `#map=<zoom>/<lat>/<lng>&bg=<photo|pale|std>&layers=city,moj,label,mask,road`
- Mask that darkens everything outside the city
- PC and smartphone layouts (< 768 px uses bottom sheets)

## Files

| Path | Content |
| --- | --- |
| `index.html` | The page (HTML, CSS and JS in one file). Version, update date and data editions are in the `APP` constant |
| `chiban_fukuyama_2026_{0,1,2}.pmtiles` | City lot map, split into three latitude bands (north → south) to stay under GitHub's 50 MB file warning |
| `houmukyoku_fukuyama_2026_{0,1,2}.pmtiles` | MOJ registry map, same bands |
| `search.json`, `search/<n>.json` | Search index: town list, then one lot list per town loaded on demand |
| `fukuyama_mask.geojson` | World polygon with the city cut out |
| `fonts/Noto Sans Medium/*.pbf` | Glyphs for label digits (SIL OFL, see `fonts/OFL.txt`) |
| `tools/` | Data build and verification scripts |
| `plans/` | Design notes (not published) |
| `.github/workflows/pages.yml` | Deploys to GitHub Pages. Only the paths it lists are published; add new site files there |
| `.nojekyll` | Disables Jekyll if Pages is switched back to branch deployment |

### Vector tile schema

| Layer | Zoom | Geometry | Attributes |
| --- | --- | --- | --- |
| `chiban` | 15 | shared-edge lines | — |
| `chiban` | 16–17 | lot polygons, feature id = source `OBJEXOID` | `chiban` (地番), `shozai` (所在, e.g. `赤坂町大字赤坂字鳥羽`) |
| `chiban_label` | 17 | points | `chiban`, `rot` (text rotation, degrees clockwise) |
| `houmukyoku` | 15 | shared-edge lines | — |
| `houmukyoku` | 16–17 | lot polygons, sequential feature id | `chiban`, `oaza`, `chome`, `koaza`, `zumei` (地図名) |
| `houmukyoku_label` | 17 | points | `chiban` |

At zoom 15 nothing is clickable, so each shared lot edge is stored once as a
line; that halves the vertex count. Zoom 18+ over-zooms the z17 tiles.

## Data sources and terms

Check each provider's current terms before publishing an update.

| Data | Provider / terms | Notes |
| --- | --- | --- |
| [地理院タイル](https://maps.gsi.go.jp/development/ichiran.html) (seamlessphoto, std, pale) | 国土地理院. Credit 「国土地理院」 and link to the tile list | z9–13 of seamlessphoto are Landsat mosaics with an extra credit; the page adds it below zoom 14. No prefetching (`prefetchZoomDelta: 0`) |
| [最適化ベクトルタイル](https://github.com/gsi-cyberjapan/optimal_bvmap) (PMTiles edition) | 国土地理院. 国土地理院コンテンツ利用規約; credit e.g. 「国土地理院最適化ベクトルタイル」 | Test release; URL and attributes may change. Read directly from GSI with HTTP Range. Uses `RdCL` (`vt_rdctg` = 国道, 高速自動車国道等, 都道府県道) and `RdEdg`; `vt_flag17 = 2` features are skipped because z16 tiles also carry z17 copies |
| [福山市地番図データ（2026年度）](https://data.city.fukuyama.hiroshima.jp/dataset/digital_numbers_map) | 福山市. 公共データ利用規約 第1.0版 (PDL1.0) | As of 2026-01-01. Tax-assessment map, not a survey. Shapefile without `.prj`; it is JGD2011 plane rectangular zone III (EPSG:6671) |
| [登記所備付地図データ 福山市](https://www.geospatial.jp/ckan/dataset/houmusyouchizu-2026-1-1553) | 法務省 via G空間情報センター. 登記所備付地図データ利用規約 | 2026 edition. Arbitrary-coordinate (任意座標) sheets cannot be georeferenced and are excluded |
| [地番マスター位置参照拡張（福山市）](https://dataset.address-br.digital.go.jp/dataset/ba-o1-342076_g2-000011) | デジタル庁. PDL1.0, plus the MOJ map terms | Used for search; city parcels fill the gaps |
| [国勢調査町丁・字等別境界データセット](https://geoshape.ex.nii.ac.jp/ka/resource/34207.html) | CODH, from 「令和2年国勢調査町丁・字等別境界データ」 (e-Stat). CC BY 4.0 | City outline for the mask |
| [国土数値情報（行政区域データ）2026年](https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2026.html) | 国土交通省. CC BY 4.0 | Adds uninhabited islets the census blocks leave out |
| [MapLibre GL JS](https://maplibre.org/) 5.24.0, [PMTiles](https://github.com/protomaps/PMTiles) 4.5.0 | BSD-3-Clause | Loaded from unpkg with SRI hashes |
| Noto Sans Medium glyphs from [protomaps/basemaps-assets](https://github.com/protomaps/basemaps-assets) | SIL OFL 1.1 | |

Both PDL1.0 and the MOJ terms require stating that the data was processed and
by whom; the page shows this in the always-visible attribution box.

### Known data quirks

- The MOJ layer covers only about 45% of the city's lots. 501 of the 842 MOJ
  sheets (about 454,000 lots) use arbitrary coordinates and cannot be
  georeferenced; they are mostly in the south and along the coast (沼隈, 内海,
  鞆, 松永, 金江, 瀬戸, 熊野, ...), while 神辺, 駅家, 新市, 加茂, 芦田 and 山野
  are fully covered.
- 27 place names in the city data contain vendor gaiji (Private Use Area code
  points) with no published mapping. They are shown as `〓`.
- Lot numbers such as `-` or `9999` come from the source as is.
- The city map and the MOJ map are different products; their lines and lots do
  not coincide, and the page says so.

## Updating the data

Raw downloads and intermediates live in `work/` and are never committed (the
repository is public; only the processed tiles are published).

1. Download into `work/raw/`:
   - City lot map zip from the city's open-data page; unzip with
     `unzip -O cp932` so that `work/raw/地番図/面/筆界_面.shp` exists
   - `34207-2404-<year>.zip` from the G-Spatial dataset page (no login needed
     for the download itself)
   - `mt_parcel_city342076.csv` and `mt_parcel_pos_city342076.csv`
     (zips from `https://data.address-br.digital.go.jp/mt_parcel/city/` and
     `.../mt_parcel_pos/city/`)
   - `r2ka34207.topojson` from
     `https://geoshape.ex.nii.ac.jp/ka/topojson/2020/34/r2ka34207.topojson`
   - `N03-<date>_34_GML.zip` from 国土数値情報, unzipped into `work/raw/N03_34/`
2. Install the tools:
   ```bash
   python3 -m venv work/.venv
   work/.venv/bin/pip install -r tools/requirements.txt
   ```
   plus [tippecanoe](https://github.com/felt/tippecanoe) (`make` from source)
   and [go-pmtiles](https://github.com/protomaps/go-pmtiles)
   (`go install github.com/protomaps/go-pmtiles@latest`).
3. Update the year and paths in `tools/build.sh` / `tools/build_data.py` if
   needed, then run `tools/build.sh`.
4. Verify:
   ```bash
   work/.venv/bin/python tools/verify_data.py --samples 20 --gsi
   ```
   This compares 20 random source lots against the served tiles and estimates
   the offset from the GSI base map.
5. Update the `APP` constant in `index.html` (file names, editions, dates).
   New PMTiles get the year in their file name so the old version can be
   restored quickly. Keep updates to about once a year; every update adds the
   full tile size to the Git history.

## Verification results (2026 data)

- 20 random lots: source shapefile and served tiles match 20/20
- City vs MOJ map, same lot number: median centroid offset 0.10 m, p99 1.6 m
- City lots vs GSI building footprints, best-fit shift in six districts
  (福山駅, 神辺, 新市, 松永, 鞆, 駅家): at most 0.5 m
- Below zoom 15 no lot tiles are requested; only each PMTiles header is read

## Local preview

PMTiles needs HTTP Range support, which `python -m http.server` lacks. Use any
static server that answers `Range` with `206 Partial Content`, for example
`npx http-server -p 8080`.
