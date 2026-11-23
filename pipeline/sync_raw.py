# Downloads every raw match JSON from S3 into data/raw/matches/ on this machine.
# Only files we don't already have get downloaded, so reruns are quick.
# Usage: uv run python pipeline/sync_raw.py
import time
from pathlib import Path

import s3

MATCH_PREFIX = "raw/matches/"

# the repo root is the folder above pipeline/; data/ is gitignored
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIR = REPO_ROOT / "data" / "raw" / "matches"


def list_match_keys():
    """Return every match file key under raw/matches/ in S3."""
    keys = []
    # S3 returns at most 1000 keys per request, so a paginator walks all the pages
    paginator = s3.client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3.bucket(), Prefix=MATCH_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                keys.append(key)
    return keys


def main():
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Listing s3://{s3.bucket()}/{MATCH_PREFIX} ...")
    keys = list_match_keys()
    print(f"  {len(keys)} matches in S3")

    # keep only the ones we don't have locally yet
    missing = []
    for key in keys:
        filename = key.split("/")[-1]  # e.g. NA1_5012345678.json
        if not (LOCAL_DIR / filename).exists():
            missing.append(key)
    print(f"  {len(missing)} to download, {len(keys) - len(missing)} already here")

    # download them one at a time, printing progress every 100 files
    start = time.monotonic()
    count = 0
    for key in missing:
        filename = key.split("/")[-1]
        s3.client().download_file(s3.bucket(), key, str(LOCAL_DIR / filename))
        count += 1
        if count % 100 == 0 or count == len(missing):
            print(f"  [{count}/{len(missing)}] {time.monotonic() - start:5.1f}s")

    print(f"Done. Local copy: {LOCAL_DIR}")


if __name__ == "__main__":
    main()
