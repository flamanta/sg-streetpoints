"""Build vector tiles for the LTA lamp posts (126,144 points, too many for plain GeoJSON).

Writes <out>/{z}/{x}/{y}.pbf for zoom 15 and 16 only. The map shows regional cards below zoom 15,
and MapLibre stretches the zoom 16 tiles for the closer zooms (up to 18).

Tiles are written uncompressed on purpose: GitHub Pages cannot send a `Content-Encoding: gzip`
header, so gzipped tiles would not decode in the browser. Pages gzips the response itself.

Nothing is dropped or simplified (`-r1`, no feature or size limits). After the build every
UNIQUE_ID in the source must be present at both zoom levels, or the script fails: tippecanoe
repeats points near tile edges, so counting features would give a misleading number.

Needs tippecanoe (which also installs tippecanoe-decode) on PATH.

Usage: build_tiles.py [--data-dir data] [--out site/tiles]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

LAYER = "lta_lamp_post"
MIN_ZOOM, MAX_ZOOM = 15, 16
ID_PATTERN = re.compile(r'"UNIQUE_ID": (\d+)')


def tool(name):
    path = shutil.which(name)
    if not path:
        sys.exit(f"{name} not found on PATH (install tippecanoe: https://github.com/felt/tippecanoe)")
    return path


def build(src, out):
    if out.exists():
        shutil.rmtree(out)  # tippecanoe -e refuses to write into an existing directory
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            tool("tippecanoe"), "-e", str(out), "-l", LAYER,
            f"-Z{MIN_ZOOM}", f"-z{MAX_ZOOM}",
            "--no-tile-compression", "-r1", "--no-feature-limit", "--no-tile-size-limit",
            "-q", str(src),
        ],
        check=True,
    )


def check(src, out):
    expected = {f["properties"]["UNIQUE_ID"] for f in json.loads(src.read_text())["features"]}
    decode = tool("tippecanoe-decode")
    for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
        run = subprocess.run([decode, f"-Z{zoom}", f"-z{zoom}", str(out)], capture_output=True, text=True, check=True)
        found = {int(i) for i in ID_PATTERN.findall(run.stdout)}
        if found != expected:
            sys.exit(f"zoom {zoom}: {len(expected - found)} points missing, {len(found - expected)} unexpected")
        print(f"zoom {zoom}: all {len(found):,} points present")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="site/tiles")
    args = ap.parse_args()
    src = Path(args.data_dir) / f"{LAYER}.geojson"
    out = Path(args.out)
    build(src, out)
    check(src, out)
    tiles = list(out.rglob("*.pbf"))
    size = sum(t.stat().st_size for t in tiles)
    print(f"{out}: {len(tiles):,} tiles, {size / 1e6:.1f} MB, largest {max(t.stat().st_size for t in tiles) / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
