import time

import s3
from riot_client import RiotClient

SEED_GAME_NAME = "fionaapple21"
SEED_TAG_LINE = "IKNOW"
REGION = "americas"
QUEUE = 420
PAGE_SIZE = 100          # Match-V5 max per request
MAX_MATCHES = 1000        # how many of YOUR matches to pull

MATCH_PREFIX = "raw/matches"


def match_key(match_id: str) -> str:
    return f"{MATCH_PREFIX}/{match_id}.json"


def main():
    client = RiotClient(region=REGION)
    account = client.get_account_by_riot_id(SEED_GAME_NAME, SEED_TAG_LINE)
    puuid = account["puuid"]
    print(f"Your PUUID: {puuid[:20]}...")

    fetched = 0
    start = 0
    start_t = time.monotonic()

    while fetched < MAX_MATCHES:
        ids = client.get_match_ids_by_puuid(
            puuid, start=start, count=PAGE_SIZE, queue=QUEUE
        )
        if not ids:
            print("No more matches in your history.")
            break

        for match_id in ids:
            if fetched >= MAX_MATCHES:
                break
            if s3.object_exists(match_key(match_id)):
                fetched += 1
                start += 1
                continue
            match = client.get_match(match_id)
            s3.put_json(match_key(match_id), match)
            fetched += 1
            start += 1
            print(f"[{fetched:3}/{MAX_MATCHES}] {match_id}  "
                  f"{time.monotonic() - start_t:5.1f}s")

    client.close()
    print(f"\nDone. Pulled {fetched} of your matches into s3://{s3.bucket()}/{MATCH_PREFIX}")


if __name__ == "__main__":
    main()
