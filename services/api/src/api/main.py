import uvicorn
from fastapi import FastAPI, HTTPException
from common.ddragon import get_latest_version, get_champions
from common.db import query

app = FastAPI(title="LoL Matchup Analytics")

K = 20.0  # shrinkage prior strength, matching the notebook


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/matchup")
def matchup(champion: str, opponent: str, lane: str):
    """Population matchup: shrunk win rate + sample size."""
    rows = query(
        "SELECT games, wins, winrate FROM matchup_stats "
        "WHERE champion=%s AND opponent=%s AND lane=%s",
        (champion, opponent, lane.upper()),
    )
    if not rows:
        raise HTTPException(404, "No data for that matchup")
    r = rows[0]
    base = query(
        "SELECT winrate FROM champion_lane_stats WHERE champion=%s AND lane=%s",
        (champion, lane.upper()),
    )
    prior = float(base[0]["winrate"]) if base else 0.5
    shrunk = (r["wins"] + K * prior) / (r["games"] + K)
    return {
        "champion": champion,
        "opponent": opponent,
        "lane": lane.upper(),
        "games": r["games"],
        "raw_winrate": round(r["wins"] / r["games"], 3),
        "shrunk_winrate": round(shrunk, 3),
        "confidence": "high" if r["games"] >= 30 else "medium" if r["games"] >= 10 else "low",
    }


@app.get("/items")
def items(champion: str, min_games: int = 10):
    """Top items for a champion by shrunk edge."""
    rows = query(
        "SELECT item_name, games, wins, winrate FROM item_stats "
        "WHERE champion=%s AND games >= %s ORDER BY games DESC",
        (champion, min_games),
    )
    if not rows:
        raise HTTPException(404, "No item data for that champion")
    base = query(
        "SELECT sum(games) g, sum(wins) w FROM champion_lane_stats WHERE champion=%s",
        (champion,),
    )
    prior = float(base[0]["w"]) / float(base[0]["g"]) if base and base[0]["g"] else 0.5
    out = []
    for r in rows:
        shrunk = (r["wins"] + K * prior) / (r["games"] + K)
        out.append({
            "item": r["item_name"],
            "games": r["games"],
            "shrunk_winrate": round(shrunk, 3),
            "edge": round(shrunk - prior, 3),
        })
    out.sort(key=lambda x: x["edge"], reverse=True)
    return {"champion": champion, "prior": round(prior, 3), "items": out}

_champion_cache = None

@app.get("/champions")
def champions():
    """Sorted list of champion display names, for the UI dropdowns."""
    global _champion_cache
    if _champion_cache is None:
        version = get_latest_version()
        champs = get_champions(version)
        _champion_cache = sorted(c["name"] for c in champs.values())
    return {"champions": _champion_cache}

@app.get("/personal")
def personal(champion: str, opponent: str, lane: str):
    """Your personal edge in a matchup vs the population baseline."""
    rows = query(
        "SELECT games, wins, raw_winrate, population_winrate, shrunk_winrate, edge "
        "FROM personal_matchup_stats WHERE champion=%s AND opponent=%s AND lane=%s",
        (champion, opponent, lane.upper()),
    )
    if not rows:
        raise HTTPException(404, "You haven't played this matchup")
    r = rows[0]
    return {
        "champion": champion, "opponent": opponent, "lane": lane.upper(),
        "games": r["games"],
        "raw_winrate": float(r["raw_winrate"]),
        "population_winrate": float(r["population_winrate"]),
        "shrunk_winrate": float(r["shrunk_winrate"]),
        "edge": float(r["edge"]),
        "verdict": ("you outperform here" if float(r["edge"]) > 0.03
                    else "you underperform here" if float(r["edge"]) < -0.03
                    else "about average for you"),
    }


def run():
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()