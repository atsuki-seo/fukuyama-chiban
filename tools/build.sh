#!/usr/bin/env bash
# Rebuild every served data file from the raw downloads in work/raw/.
# See README.md ("データの更新手順") for where each input comes from.
set -euo pipefail

cd "$(dirname "$0")/.."
YEAR="${YEAR:-2026}"
PY="${PY:-work/.venv/bin/python}"
MOJXML="${MOJXML:-work/.venv/bin/mojxml2ogr}"
TIPPECANOE="${TIPPECANOE:-tippecanoe}"
PMTILES="${PMTILES:-go-pmtiles}"

mkdir -p work/mid

# Public-coordinate sheets only: mojxml2ogr skips 任意座標系 unless -a is given.
if [[ ! -f work/mid/houmukyoku_raw.fgb || work/raw/34207-2404-${YEAR}.zip -nt work/mid/houmukyoku_raw.fgb ]]; then
  "$MOJXML" work/mid/houmukyoku_raw.fgb "work/raw/34207-2404-${YEAR}.zip"
fi

"$PY" tools/build_data.py city moj mask search

# -pf -pk: never drop parcels to fit tile limits.
# --low-detail=10: z15-16 tiles get a ~1 m grid, finer than a screen pixel
# there; z17 keeps the full 4096 grid (~6 cm) for overzooming.
# --detect-shared-borders: simplify shared edges identically so neighbouring
# parcels do not show gaps at z16.
common=(-q -Z15 -z17 -pf -pk --low-detail=10 --detect-shared-borders -P --force)
parts=$(ls work/mid/chiban_city.*.geojsonl | wc -l)

rm -f chiban_fukuyama_*.pmtiles houmukyoku_fukuyama_*.pmtiles
for ((k = 0; k < parts; k++)); do
  "$TIPPECANOE" "${common[@]}" -o "chiban_fukuyama_${YEAR}_${k}.pmtiles" \
    -n "福山市地番図 ${YEAR} (${k})" \
    -L chiban:work/mid/chiban_city_edges.${k}.geojsonl \
    -L chiban:work/mid/chiban_city.${k}.geojsonl \
    -L chiban_label:work/mid/chiban_city_label.${k}.geojsonl

  "$TIPPECANOE" "${common[@]}" -o "houmukyoku_fukuyama_${YEAR}_${k}.pmtiles" \
    -n "登記所備付地図 福山市 ${YEAR} (${k})" \
    -L houmukyoku:work/mid/houmukyoku_edges.${k}.geojsonl \
    -L houmukyoku:work/mid/houmukyoku.${k}.geojsonl \
    -L houmukyoku_label:work/mid/houmukyoku_label.${k}.geojsonl
done

for f in chiban_fukuyama_${YEAR}_*.pmtiles houmukyoku_fukuyama_${YEAR}_*.pmtiles; do
  "$PMTILES" show "$f" | grep -E "bounds|zoom|tile entries"
  ls -l "$f"
done
