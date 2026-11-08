"""Summarise the point layers into five regions and write data/<name>_regions.geojson.

The web map shows these five bubbles (name and count) when zoomed out and swaps to the
individual points when zoomed in. Each point goes to the nearest anchor below, and the
bubble sits at the average position of its points.

Usage: make_regions.py [--data-dir data]
"""
import argparse
import json
import sys
from pathlib import Path

LAYERS = ["lta_lamp_post", "lta_bus_stop"]

# Anchor (lat, lon) for each region. These are hand-picked, not official boundaries: Central is
# around Toa Payoh and Bishan, South is the city and harbour, and North, East and West are
# Woodlands, Tampines and Jurong.
ANCHORS = {
    "North": (1.430, 103.805),
    "South": (1.275, 103.835),
    "East": (1.350, 103.940),
    "West": (1.340, 103.690),
    "Central": (1.340, 103.835),
}


def nearest(lon, lat):
    return min(ANCHORS, key=lambda n: (lat - ANCHORS[n][0]) ** 2 + (lon - ANCHORS[n][1]) ** 2)


def build(src, out):
    features = json.loads(src.read_text())["features"]
    if not features:
        sys.exit(f"{src}: no points to summarise")
    members = {name: [] for name in ANCHORS}
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        members[nearest(lon, lat)].append((lon, lat))

    regions = []
    for name, pts in members.items():
        if not pts:
            continue
        regions.append({
            "type": "Feature",
            "properties": {"name": name, "count": len(pts)},
            "geometry": {
                "type": "Point",
                "coordinates": [
                    round(sum(p[0] for p in pts) / len(pts), 6),
                    round(sum(p[1] for p in pts) / len(pts), 6),
                ],
            },
        })
    out.write_text(json.dumps({"type": "FeatureCollection", "features": regions}, separators=(",", ":")) + "\n")
    print(f"{out.name}: " + ", ".join(f"{r['properties']['name']} {r['properties']['count']:,}" for r in regions))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    data = Path(ap.parse_args().data_dir)
    for name in LAYERS:
        build(data / f"{name}.geojson", data / f"{name}_regions.geojson")


if __name__ == "__main__":
    main()
