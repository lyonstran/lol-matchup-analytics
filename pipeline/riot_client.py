import time
from urllib.parse import quote

import httpx

from config import get_riot_api_key
from rate_limiter import RateLimiter

DEV_KEY_LIMITS = [(20, 1), (100, 120)]
RETRYABLE_STATUS = {500, 502, 503, 504}


class RiotAPIError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(f"Riot API {status_code}: {message}")


class RiotClient:
    def __init__(self, region="americas", api_key=None, limits=None, max_retries=3):
        self.base = f"https://{region}.api.riotgames.com"
        self.limiter = RateLimiter(limits or DEV_KEY_LIMITS)
        self.max_retries = max_retries
        self.client = httpx.Client(
            headers={"X-Riot-Token": api_key or get_riot_api_key()},
            timeout=15,
        )

    def _get(self, url, params=None):
        last = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            resp = self.client.get(url, params=params)
            last = resp
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                print(f"  [429] rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            if resp.status_code in RETRYABLE_STATUS:
                backoff = 2 ** attempt
                print(f"  [{resp.status_code}] server error, retry in {backoff}s")
                time.sleep(backoff)
                continue
            raise RiotAPIError(resp.status_code, resp.text)  # 4xx: fail fast
        raise RiotAPIError(last.status_code, f"exhausted retries: {last.text}")

    # --- Account-V1 (regional routing) ---
    def get_account_by_riot_id(self, game_name, tag_line):
        url = f"{self.base}/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        return self._get(url)

    # --- Match-V5 (regional routing) ---
    def get_match_ids_by_puuid(self, puuid, start=0, count=20, queue=None):
        params = {"start": start, "count": count}
        if queue is not None:
            params["queue"] = queue
        return self._get(f"{self.base}/lol/match/v5/matches/by-puuid/{puuid}/ids", params=params)

    def get_match(self, match_id):
        return self._get(f"{self.base}/lol/match/v5/matches/{match_id}")

    def close(self):
        self.client.close()
