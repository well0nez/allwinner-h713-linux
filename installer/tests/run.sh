#!/bin/bash
# run.sh [--local] [--slow] [--old]  -- the golden suite in its modes (see README.md).
#   default : the tools next to this directory (the package), repository fixtures only (vendor tests skip)
#   --local : Marco's machine -- vendor fixtures and the three vendor images (umbau/fixtures-local, ~/Downloads)
#   --slow  : also the extractor runs over the full images (H713_SLOW_TESTS=1)
#   --old   : the stand-alone scripts of v0.5-beta instead of the package (to re-freeze a golden value)
set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ARBEIT=/opt/Projekte/h713/analyse/release/arbeit
for a in "$@"; do
  case "$a" in
    --local) export H713_FIXTURES_LOCAL=/opt/Projekte/h713/umbau/fixtures-local H713_BUILD_OUT=$ARBEIT/r0-fel/out H713_VENDOR_OUT=$ARBEIT/r2-extract/out-hy310-20260912 ;;
    --slow)  export H713_SLOW_TESTS=1 ;;
    --old)   export H713_TOOLS_DIR=$ARBEIT/r0-fel H713_EXTRACT_PATH=$ARBEIT/r2-extract/h713-extract ;;
    *) echo "usage: run.sh [--local] [--slow] [--old]" >&2; exit 2 ;;
  esac
done
cd "$HERE" && exec python3 -m unittest discover -s . "${VERBOSE:+-v}"
