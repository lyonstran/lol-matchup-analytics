import json
import os
import time
from collections import deque
from pathlib import Path

import s3
from riot_client import RiotClient

# --- config ---
# Start from your own PUUID. Riot IDs can be renamed (the old seed, "jefff buckley#GRACE",
# no longer exists), but a PUUID never changes, and you play often, so your games are fresh.
SEED_PUUID = os.environ.get("MY_PUUID", "")
REGION = "americas"
QUEUE = 420                   # ranked solo/duo
MATCHES_PER_PLAYER = 10
MAX_MATCHES = int(os.environ.get("MAX_MATCHES", "100"))
MAX_PLAYERS = 1000            # safety stop: never look up more players than this in one run
MATCH_PREFIX = "raw/matches"

# local copy of S3 kept up to date by sync_raw.py (run that first)
LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "matches"


def match_key(match_id: str) -> str:
    return f"{MATCH_PREFIX}/{match_id}.json"


def local_path(match_id: str) -> Path:
    return LOCAL_DIR / f"{match_id}.json"


def already_have(match_id: str) -> bool:
    """Check the local copy first (free and fast), then S3 (the source of truth)."""
    if local_path(match_id).exists():
        return True
    return s3.object_exists(match_key(match_id))


def save_match(match_id: str, data: dict) -> None:
    """Store in S3 (permanent) and in the local copy (so build.py sees it right away)."""
    s3.put_json(match_key(match_id), data)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(local_path(match_id), "w", encoding="utf-8") as f:
        json.dump(data, f)


def known_participants(match_id: str) -> list:
    """Players in a match we already have, read from the local copy (empty if not local)."""
    path = local_path(match_id)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        match = json.load(f)
    return match["metadata"]["participants"]


def main():
    if not SEED_PUUID:
        raise RuntimeError("MY_PUUID is not set. Add it to .env (or the GitHub secret).")
    print(f"Target: {MAX_MATCHES} new matches, queue={QUEUE}\n")
    client = RiotClient(region=REGION)

    frontier = deque([SEED_PUUID])
    seen_puuids = {SEED_PUUID}
    fetched = 0
    players_checked = 0
    start = time.monotonic()

    while frontier and fetched < MAX_MATCHES and players_checked < MAX_PLAYERS:
        puuid = frontier.popleft()
        players_checked += 1
        match_ids = client.get_match_ids_by_puuid(
            puuid, count=MATCHES_PER_PLAYER, queue=QUEUE
        )
        for match_id in match_ids:
            if fetched >= MAX_MATCHES:
                break

            if already_have(match_id):
                # no download, but still walk through it to reach new players
                participants = known_participants(match_id)
            else:
                match = client.get_match(match_id)
                save_match(match_id, match)
                fetched += 1
                participants = match["metadata"]["participants"]
                elapsed = time.monotonic() - start
                print(f"[{fetched:3}/{MAX_MATCHES}] {match_id}  "
                      f"frontier={len(frontier)}  {elapsed:5.1f}s")

            for p in participants:
                if p not in seen_puuids:
                    seen_puuids.add(p)
                    frontier.append(p)

    client.close()
    print(f"\nDone. {fetched} new matches in s3://{s3.bucket()}/{MATCH_PREFIX} "
          f"({players_checked} players checked)")


if __name__ == "__main__":
    main()
