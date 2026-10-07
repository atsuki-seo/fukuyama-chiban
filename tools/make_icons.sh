#!/bin/sh
# Render the PWA icons in icons/ from their SVG sources.
# Needs rsvg-convert (librsvg): brew install librsvg
set -eu
cd "$(dirname "$0")/../icons"
rsvg-convert -w 192 -h 192 icon.svg -o icon-192.png
rsvg-convert -w 512 -h 512 icon.svg -o icon-512.png
rsvg-convert -w 512 -h 512 icon-maskable.svg -o icon-maskable-512.png
rsvg-convert -w 180 -h 180 apple-touch-icon.svg -o apple-touch-icon.png
ls -l *.png
