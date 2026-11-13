"""Assemble the MapLibre web map into <out> (default site/), ready for GitHub Pages.

  site/index.html          from web/index.html
  site/data/*.geojson      bus stops, SLA lamp posts and the three regional summaries. The bus stop file
                           loses its lat/lon text properties (see slim_points); the page shows the
                           coordinates from the geometry instead
  site/tiles/{z}/{x}/{y}.pbf   LTA lamp posts, from build_tiles.py
  site/lib/maplibre-gl.*   MapLibre GL JS, pinned to one version and checked against a SHA-256

The 22 MB LTA lamp post GeoJSON is not copied: the map only reads it through the tiles.

Usage: build_site.py [--data-dir data] [--out site]
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAPLIBRE_VERSION = "4.7.1"
MAPLIBRE_FILES = {
    "maplibre-gl.js": "be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1",
    "maplibre-gl.css": "576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9",
}
CDN = "https://cdn.jsdelivr.net/npm/maplibre-gl@{version}/dist/{name}"

# The bus stop popup shows lat/lon from the geometry, so the 8-decimal text copies are dropped from this file
# to save about a quarter of the download. The other layers keep them: the LTA lamp posts reach the page through
# tiles (geometry only accurate to about 15 cm), and the SLA file is so small (268 points) that dropping them
# saved 2 KB but, measured, made the first view slower.
POINT_FILES = ["lta_bus_stop.geojson"]

DATA_FILES = [
    "sla_lamp_post.geojson",
    "lta_lamp_post_regions.geojson",
    "sla_lamp_post_regions.geojson",
    "lta_bus_stop_regions.geojson",
]


def fetch_maplibre(lib):
    lib.mkdir(parents=True, exist_ok=True)
    for name, sha in MAPLIBRE_FILES.items():
        req = urllib.request.Request(
            CDN.format(version=MAPLIBRE_VERSION, name=name), headers={"User-Agent": "sg-streetpoints-build"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        got = hashlib.sha256(body).hexdigest()
        if got != sha:
            sys.exit(f"{name}: SHA-256 {got} does not match the pinned {sha}")
        (lib / name).write_bytes(body)
        print(f"lib/{name}: {len(body) / 1e3:.0f} KB, checksum ok")


def slim_points(src, dst):
    """Copy a point file without its lat/lon text properties.

    The page shows the geometry's coordinates formatted to 8 decimals in their place, so first check
    that this gives exactly the text being dropped, for every point. If not, fail the build.
    """
    fc = json.loads(src.read_text())
    for f in fc["features"]:
        lon, lat = f["geometry"]["coordinates"]
        props = f["properties"]
        if f"{lon:.8f}" != props.get("lon") or f"{lat:.8f}" != props.get("lat"):
            sys.exit(f"{src.name}: coordinates {lon}, {lat} do not match lat/lon text {props.get('lat')}, {props.get('lon')}")
        del props["lat"], props["lon"]
    dst.write_text(json.dumps(fc, separators=(",", ":")) + "\n")
    print(f"{dst.name}: {len(fc['features']):,} points, lat/lon text checked and dropped")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    args = ap.parse_args()
    data, out = Path(args.data_dir), Path(args.out)

    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)

    shutil.copy(ROOT / "web" / "index.html", out / "index.html")
    for name in DATA_FILES:
        shutil.copy(data / name, out / "data" / name)
    for name in POINT_FILES:
        slim_points(data / name, out / "data" / name)
    fetch_maplibre(out / "lib")
    subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts" / "build_tiles.py"), "--data-dir", str(data), "--out", str(out / "tiles")],
        check=True,
    )
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"{out}: {total / 1e6:.1f} MB in total")


if __name__ == "__main__":
    main()
