from common.athena import run_query
from common.db import upsert
from common.ddragon import get_latest_version, get_items, build_item_id_map

ITEM_SQL = """
WITH players AS (
  SELECT
    p.championName AS champion,
    p.win AS win,
    array[p.item0, p.item1, p.item2, p.item3, p.item4, p.item5] AS items
  FROM raw_matches
  CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.teamPosition <> ''
)
SELECT
  champion,
  item_id,
  count(*) AS games,
  sum(CASE WHEN win THEN 1 ELSE 0 END) AS wins
FROM players
CROSS JOIN UNNEST(items) AS u(item_id)
WHERE item_id <> 0
GROUP BY champion, item_id
"""


def main():
    version = get_latest_version()
    items_raw = get_items(version)
    names = build_item_id_map(items_raw)

    completed = {
        int(iid)
        for iid, meta in items_raw.items()
        if not meta.get("into")
        and meta.get("gold", {}).get("total", 0) >= 2000
        and meta.get("gold", {}).get("purchasable", True)
    }
    print(f"{len(completed)} completed items in patch {version}")

    print("Running item aggregation in Athena...")
    rows = run_query(ITEM_SQL)

    cleaned = []
    for r in rows:
        item_id = int(r["item_id"])
        if item_id not in completed:
            continue
        games = int(r["games"])
        wins = int(r["wins"])
        cleaned.append({
            "champion": r["champion"],
            "item_id": item_id,
            "item_name": names.get(item_id, str(item_id)),
            "games": games,
            "wins": wins,
            "winrate": round(wins / games, 3),
        })

    n = upsert(
        "item_stats",
        ["champion", "item_id", "item_name", "games", "wins", "winrate"],
        ["champion", "item_id"],
        cleaned,
    )
    print(f"Upserted {n} champion-item rows")


if __name__ == "__main__":
    main()