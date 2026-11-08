"""Download each configured data.gov.sg dataset to raw/ and report whether it changed.

Usage: fetch_geojson.py [--raw-dir raw] [--hashes data/.source-hashes.json]
Prints "changed" or "unchanged" on the last line; also writes it to $GITHUB_OUTPUT.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"
RATE_LIMITED = 24
MAX_ATTEMPTS = 6
RETRY_STATUS = {429, 500, 502, 503, 504}


def get(url, api_key=None):
    """GET a URL, retrying timeouts, dropped connections and temporary server errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "sg-streetpoints"})
    if api_key:
        req.add_header("x-api-key", api_key)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                raise
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == MAX_ATTEMPTS:
                raise
            reason = str(getattr(e, "reason", e))
        # the download link is signed, so log only the part before the query string
        print(f"attempt {attempt} failed for {url.split('?')[0]} ({reason}); retrying", flush=True)
        time.sleep(5 * attempt)


def download_url(dataset_id, api_key):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            body = json.loads(get(POLL_URL.format(dataset_id), api_key))
        except urllib.error.HTTPError as e:
            body = {"code": e.code, "errorMsg": str(e)}
        if body.get("code") == 0:
            return body["data"]["url"]
        if attempt == MAX_ATTEMPTS:
            sys.exit(f"{dataset_id}: poll-download failed: {body.get('errorMsg')}")
        # rate limit says "try again in 10 seconds"
        time.sleep(12 * attempt if body.get("code") == RATE_LIMITED else 5 * attempt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/datasets.json")
    ap.add_argument("--raw-dir", default="raw")
    ap.add_argument("--hashes", default="data/.source-hashes.json")
    args = ap.parse_args()

    api_key = os.environ.get("DATA_GOV_SG_API_KEY")
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    hashes_path = Path(args.hashes)
    old = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
    new = {}

    for ds in json.loads(Path(args.config).read_text()):
        data = get(download_url(ds["dataset_id"], api_key))
        (raw_dir / f"{ds['name']}.geojson").write_bytes(data)
        new[ds["name"]] = hashlib.sha256(data).hexdigest()
        print(f"{ds['name']}: {len(data):,} bytes")

    changed = new != old
    hashes_path.parent.mkdir(parents=True, exist_ok=True)
    hashes_path.write_text(json.dumps(new, indent=2) + "\n")
    result = "changed" if changed else "unchanged"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"result={result}\n")
    print(result)


if __name__ == "__main__":
    main()
