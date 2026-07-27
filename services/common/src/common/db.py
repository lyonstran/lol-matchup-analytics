import os

import psycopg
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in .env")
    return url


def connect():
    """Open a Postgres connection. Caller manages the context/commit."""
    return psycopg.connect(get_database_url())