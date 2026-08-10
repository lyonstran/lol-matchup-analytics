import os
from dotenv import load_dotenv, find_dotenv

from common.athena import run_query
from common.db import upsert, query

load_dotenv(find_dotenv())

MY_PUUID = os.environ["MY_PUUID"]
K = 20.0

PERSONAL_SQL = f"""
WITH me AS (
  SELECT metadata.matchId AS match_id, p.championName AS champion,
         p.teamId AS team_id, p.teamPosition AS lane, p.win AS win
  FROM raw_matches CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.puuid = '{MY_PUUID}' AND p.teamPosition <> ''
),
opp AS (
  SELECT metadata.matchId AS match_id, p.championName AS champion,
         p.teamId AS team_id, p.teamPosition AS lane
  FROM raw_matches CROSS JOIN UNNEST(info.participants) AS t(p)
  WHERE p.teamPosition <> ''
)
SELECT me.champion AS champion, opp.champion AS opponent, me.lane AS lane,
       count(*) AS games, sum(CASE WHEN me.win THEN 1 ELSE 0 END) AS wins
FROM me JOIN opp
  ON me.match_id = opp.match_id AND me.lane = opp.lane AND me.team_id <> opp.team_id
GROUP BY me.champion, opp.champion, me.lane
"""


def main():
    # Load the ALREADY-SHRUNK population matchup rates as the prior (hierarchical)
    pop = query("SELECT champion, opponent, lane, games, wins FROM matchup_stats")
    base = query("SELECT champion, lane, winrate FROM champion_lane_stats")

    # population shrunk rate per matchup cell
    base_lookup = {(b["champion"], b["lane"]): float(b["winrate"]) for b in base}
    pop_shrunk = {}
    for r in pop:
        prior = base_lookup.get((r["champion"], r["lane"]), 0.5)
        s = (r["wins"] + K * prior) / (r["games"] + K)
        pop_shrunk[(r["champion"], r["opponent"], r["lane"])] = s

    print("Running personal aggregation in Athena...")
    rows = run_query(PERSONAL_SQL)

    cleaned = []
    for r in rows:
        champ, opp, lane = r["champion"], r["opponent"], r["lane"]
        games, wins = int(r["games"]), int(r["wins"])
        prior = pop_shrunk.get((champ, opp, lane))
        if prior is None:
            prior = base_lookup.get((champ, lane), 0.5)
        shrunk = (wins + K * prior) / (games + K)
        cleaned.append({
            "champion": champ, "opponent": opp, "lane": lane,
            "games": games, "wins": wins,
            "raw_winrate": round(wins / games, 3),
            "population_winrate": round(prior, 3),
            "shrunk_winrate": round(shrunk, 3),
            "edge": round(shrunk - prior, 3),
        })

    n = upsert(
        "personal_matchup_stats",
        ["champion", "opponent", "lane", "games", "wins",
         "raw_winrate", "population_winrate", "shrunk_winrate", "edge"],
        ["champion", "opponent", "lane"],
        cleaned,
    )
    print(f"Upserted {n} personal matchup rows")


if __name__ == "__main__":
    main()