import time
from collections import deque

from common import s3
from common.riot_client import RiotClient

# --- config ---
SEED_GAME_NAME = "jefff buckley"
SEED_TAG_LINE = "GRACE"
REGION = "americas"
QUEUE = 420                   # ranked solo/duo
MATCHES_PER_PLAYER = 10
MAX_MATCHES = 500

MATCH_PREFIX = "raw/matches"


def match_key(match_id: str) -> str:
    return f"{MATCH_PREFIX}/{match_id}.json"


def already_have(match_id: str) -> bool:
    return s3.object_exists(match_key(match_id))


def save_match(match_id: str, data: dict) -> None:
    s3.put_json(match_key(match_id), data)


def main():
    client = RiotClient(region=REGION)

    account = client.get_account_by_riot_id(SEED_GAME_NAME, SEED_TAG_LINE)
    seed_puuid = account["puuid"]

    frontier = deque([seed_puuid])
    seen_puuids = {seed_puuid}
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

            for p in match["metadata"]["participants"]:
                if p not in seen_puuids:
                    seen_puuids.add(p)
                    frontier.append(p)

            elapsed = time.monotonic() - start
            print(f"[{fetched:3}/{MAX_MATCHES}] {match_id}  "
                  f"frontier={len(frontier)}  {elapsed:5.1f}s")

    client.close()
    print(f"\nDone. {fetched} matches in s3://{s3.bucket()}/{MATCH_PREFIX}")


if __name__ == "__main__":
    main()