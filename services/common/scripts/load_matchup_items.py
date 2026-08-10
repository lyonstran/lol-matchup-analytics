from common.athena import run_query
from common.db import upsert
from common.ddragon import get_latest_version, get_items, build_item_id_map

MATCHUP_ITEM_SQL = """
WITH me AS (
  SELECT metadata.matchId AS match_id, p.championName AS champion,
         p.teamId AS team_id, p.teamPosition AS lane, p.win AS win,
         array[p.item0,p.item1,p.item2,p.item3,p.item4,p.item5] AS items
  FROM raw_matches CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.teamPosition <> ''
),
opp AS (
  SELECT metadata.matchId AS match_id, p.championName AS champion,
         p.teamId AS team_id, p.teamPosition AS lane
  FROM raw_matches CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.teamPosition <> ''
)
SELECT me.champion AS champion, opp.champion AS opponent, me.lane AS lane,
       item_id, count(*) AS games,
       sum(CASE WHEN me.win THEN 1 ELSE 0 END) AS wins
FROM me
JOIN opp ON me.match_id = opp.match_id AND me.lane = opp.lane AND me.team_id <> opp.team_id
CROSS JOIN UNNEST(me.items) AS u(item_id)
WHERE item_id <> 0
GROUP BY me.champion, opp.champion, me.lane, item_id
"""


def main():
    version = get_latest_version()
    items_raw = get_items(version)
    names = build_item_id_map(items_raw)
    completed = {
        int(iid) for iid, meta in items_raw.items()
        if not meta.get("into")
        and meta.get("gold", {}).get("total", 0) >= 2000
        and meta.get("gold", {}).get("purchasable", True)
    }

    print("Running matchup-item aggregation in Athena...")
    rows = run_query(MATCHUP_ITEM_SQL)

    cleaned = []
    for r in rows:
        item_id = int(r["item_id"])
        if item_id not in completed:
            continue
        cleaned.append({
            "champion": r["champion"], "opponent": r["opponent"], "lane": r["lane"],
            "item_id": item_id, "item_name": names.get(item_id, str(item_id)),
            "games": int(r["games"]), "wins": int(r["wins"]),
        })

    n = upsert(
        "matchup_item_stats",
        ["champion", "opponent", "lane", "item_id", "item_name", "games", "wins"],
        ["champion", "opponent", "lane", "item_id"],
        cleaned,
    )
    print(f"Upserted {n} matchup-item rows")


if __name__ == "__main__":
    main()