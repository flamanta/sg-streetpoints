"""Turn raw/*.geojson into slim data/*.geojson with lat/lon injected as properties.

Usage: inject_latlon.py [--raw-dir raw] [--out-dir data]
Fails (without touching existing output) if any dataset is empty or not all Points.
"""
import argparse
import json
import sys
from pathlib import Path

PRECISION = 8  # ~1 mm


def slim(ds, raw):
    if raw.get("type") != "FeatureCollection" or not raw.get("features"):
        sys.exit(f"{ds['name']}: empty or not a FeatureCollection")
    features = []
    for f in raw["features"]:
        geom = f.get("geometry")
        if not geom or geom.get("type") != "Point":
            sys.exit(f"{ds['name']}: non-Point or missing geometry")
        lon, lat = (round(c, PRECISION) for c in geom["coordinates"][:2])
        props = {k: f["properties"].get(k) for k in ds["slim_props"]}
        props["lat"], props["lon"] = lat, lon
        features.append(
            {"type": "Feature", "properties": props,
             "geometry": {"type": "Point", "coordinates": [lon, lat]}}
        )
    return {"type": "FeatureCollection", "features": features}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/datasets.json")
    ap.add_argument("--raw-dir", default="raw")
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for ds in json.loads(Path(args.config).read_text()):
        raw = json.loads((Path(args.raw_dir) / f"{ds['name']}.geojson").read_text())
        results[ds["name"]] = slim(ds, raw)
    # write only after every dataset validated
    for name, fc in results.items():
        path = out_dir / f"{name}.geojson"
        path.write_text(json.dumps(fc, separators=(",", ":")) + "\n")
        print(f"{name}: {len(fc['features']):,} features, {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
