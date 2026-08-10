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

def upsert(table: str, columns: list[str], conflict_keys: list[str], rows: list[dict]) -> int:
    """Insert rows, updating on primary-key conflict. Returns row count."""
    if not rows:
        return 0
    cols = ", ".join(columns)
    placeholders = ", ".join(f"%({c})s" for c in columns)
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict_keys
    )
    sql = (
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(conflict_keys)}) DO UPDATE SET {updates}"
    )
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    return len(rows)

def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return rows as dicts."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]