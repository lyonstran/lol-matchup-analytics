import os
import time

import s3
from crawl import already_have, save_match
from riot_client import RiotClient

# Your PUUID from .env (or the GitHub secret). It never changes, even if you rename
# your Riot ID, and build.py uses the same value to pick out your games.
MY_PUUID = os.environ.get("MY_PUUID", "")
REGION = "americas"
QUEUE = 420
PAGE_SIZE = 100          # Match-V5 max per request
MAX_MATCHES = 1000        # how many of YOUR matches to pull

MATCH_PREFIX = "raw/matches"


def main():
    if not MY_PUUID:
        raise RuntimeError("MY_PUUID is not set. Add it to .env (or the GitHub secret).")
    client = RiotClient(region=REGION)
    puuid = MY_PUUID
    print(f"Your PUUID: {puuid[:20]}...")

    checked = 0
    new = 0
    start = 0
    start_t = time.monotonic()

    while checked < MAX_MATCHES:
        ids = client.get_match_ids_by_puuid(
            puuid, start=start, count=PAGE_SIZE, queue=QUEUE
        )
        if not ids:
            print("No more matches in your history.")
            break

        for match_id in ids:
            if checked >= MAX_MATCHES:
                break
            checked += 1
            start += 1
            if already_have(match_id):
                continue
            match = client.get_match(match_id)
            save_match(match_id, match)
            new += 1
            print(f"[{checked:4}/{MAX_MATCHES}] {match_id}  "
                  f"{time.monotonic() - start_t:5.1f}s")

    client.close()
    print(f"\nDone. Checked {checked} of your matches, {new} were new "
          f"(saved to s3://{s3.bucket()}/{MATCH_PREFIX})")


if __name__ == "__main__":
    main()
