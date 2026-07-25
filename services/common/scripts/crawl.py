import json
import time
from pathlib import Path
from collections import deque

from common.riot_client import RiotClient

# --- config ---
SEED_GAME_NAME = "jefff buckley"   # same Riot ID as test_riot_client.py
SEED_TAG_LINE = "GRACE"
REGION = "americas"
QUEUE = 420                   # ranked solo/duo
MATCHES_PER_PLAYER = 10
MAX_MATCHES = 300              # small for the first run — bump up once it works

# repo_root/data/raw/matches  (scripts -> common -> services -> repo root)
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "matches"


def already_have(match_id: str) -> bool:
    return (RAW_DIR / f"{match_id}.json").exists()


def save_match(match_id: str, data: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"{match_id}.json").write_text(json.dumps(data), encoding="utf-8")


def main():
    client = RiotClient(region=REGION)

    account = client.get_account_by_riot_id(SEED_GAME_NAME, SEED_TAG_LINE)
    seed_puuid = account["puuid"]

    frontier = deque([seed_puuid])     # PUUIDs still to crawl
    seen_puuids = {seed_puuid}         # PUUIDs already queued
    fetched = 0
    start = time.monotonic()

    while frontier and fetched < MAX_MATCHES:
        puuid = frontier.popleft()
        match_ids = client.get_match_ids_by_puuid(
            puuid, count=MATCHES_PER_PLAYER, queue=QUEUE
        )
        for match_id in match_ids:
            if fetched >= MAX_MATCHES:
                break
            if already_have(match_id):
                continue

            match = client.get_match(match_id)
            save_match(match_id, match)
            fetched += 1

            # harvest the 9 other players into the frontier
            for p in match["metadata"]["participants"]:
                if p not in seen_puuids:
                    seen_puuids.add(p)
                    frontier.append(p)

            elapsed = time.monotonic() - start
            print(f"[{fetched:3}/{MAX_MATCHES}] {match_id}  "
                  f"frontier={len(frontier)}  {elapsed:5.1f}s")

    client.close()
    print(f"\nDone. {fetched} matches in {RAW_DIR}")


if __name__ == "__main__":
    main()