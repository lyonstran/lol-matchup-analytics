from common.athena import run_query
from common.db import upsert

MATCHUP_SQL = """
WITH players AS (
  SELECT
    metadata.matchId AS match_id,
    p.championName   AS champion,
    p.teamId         AS team_id,
    p.teamPosition   AS position,
    p.win            AS win
  FROM raw_matches
  CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.teamPosition <> ''
)
SELECT
  a.champion AS champion,
  b.champion AS opponent,
  a.position AS lane,
  count(*)   AS games,
  sum(CASE WHEN a.win THEN 1 ELSE 0 END) AS wins,
  round(avg(CASE WHEN a.win THEN 1.0 ELSE 0.0 END), 3) AS winrate
FROM players a
JOIN players b
  ON a.match_id = b.match_id
 AND a.position = b.position
 AND a.team_id <> b.team_id
GROUP BY a.champion, b.champion, a.position
"""

BASELINE_SQL = """
SELECT
  p.championName AS champion,
  p.teamPosition AS lane,
  count(*)       AS games,
  sum(CASE WHEN p.win THEN 1 ELSE 0 END) AS wins,
  round(avg(CASE WHEN p.win THEN 1.0 ELSE 0.0 END), 3) AS winrate
FROM raw_matches
CROSS JOIN UNNEST(info.participants) AS t(p)
WHERE p.teamPosition <> ''
GROUP BY p.championName, p.teamPosition
"""


def to_typed(rows):
    """Athena returns everything as strings; cast the numeric columns."""
    for r in rows:
        r["games"] = int(r["games"])
        r["wins"] = int(r["wins"])
        r["winrate"] = float(r["winrate"])
    return rows


def main():
    print("Running matchup aggregation in Athena...")
    matchups = to_typed(run_query(MATCHUP_SQL))
    n = upsert(
        "matchup_stats",
        ["champion", "opponent", "lane", "games", "wins", "winrate"],
        ["champion", "opponent", "lane"],
        matchups,
    )
    print(f"  upserted {n} matchup rows")

    print("Running baseline aggregation in Athena...")
    baselines = to_typed(run_query(BASELINE_SQL))
    n = upsert(
        "champion_lane_stats",
        ["champion", "lane", "games", "wins", "winrate"],
        ["champion", "lane"],
        baselines,
    )
    print(f"  upserted {n} baseline rows")

    print("Done.")


if __name__ == "__main__":
    main()