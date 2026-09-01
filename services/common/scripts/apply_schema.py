from pathlib import Path

from common.db import connect

SCHEMA = Path(__file__).resolve().parents[3] / "infra" / "sql" / "schema.sql"


def main():
    sql = SCHEMA.read_text(encoding="utf-8")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print(f"Applied schema from {SCHEMA}")


if __name__ == "__main__":
    main()