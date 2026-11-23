import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())  # walks up from cwd to the repo-root .env


def get_riot_api_key() -> str:
    key = os.environ.get("RIOT_API_KEY")
    if not key:
        raise RuntimeError("RIOT_API_KEY is not set. Add it to your .env at the repo root.")
    return key