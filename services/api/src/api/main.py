import os
import uvicorn
from fastapi import FastAPI, HTTPException
from common.ddragon import get_latest_version, get_champions
from common.db import query
from anthropic import Anthropic

app = FastAPI(title="LoL Matchup Analytics")

K = 20.0  # shrinkage prior strength, matching the notebook


@app.get("/health")
def health():
    return {"status": "ok"}


_ddragon_version = None

def ddragon_version():
    global _ddragon_version
    if _ddragon_version is None:
        _ddragon_version = get_latest_version()
    return _ddragon_version

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
        "SELECT item_id, item_name, games, wins FROM item_stats "
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
            "item_id": r["item_id"],
            "games": r["games"],
            "shrunk_winrate": round(shrunk, 3),
            "edge": round(shrunk - prior, 3),
        })
    out.sort(key=lambda x: x["edge"], reverse=True)
    return {"champion": champion, "prior": round(prior, 3), "version": ddragon_version(), "items": out}

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

_anthropic = None

@app.get("/matchup-items")
def matchup_items(champion: str, opponent: str, lane: str, min_games: int = 3):
    """Items for a champion into a specific opponent, shrunk toward the champion-wide item rate."""
    lane = lane.upper()
    rows = query(
        "SELECT item_name, item_id, games, wins FROM matchup_item_stats "
        "WHERE champion=%s AND opponent=%s AND lane=%s AND games >= %s",
        (champion, opponent, lane, min_games),
    )
    if not rows:
        raise HTTPException(404, "No matchup-specific item data")

    # prior per item = champion-wide shrunk item rate (from item_stats)
    champ_items = query(
        "SELECT item_id, games, wins FROM item_stats WHERE champion=%s",
        (champion,),
    )
    ibase = query("SELECT sum(games) g, sum(wins) w FROM champion_lane_stats WHERE champion=%s", (champion,))
    champ_prior = float(ibase[0]["w"]) / float(ibase[0]["g"]) if ibase and ibase[0]["g"] else 0.5
    item_prior = {}
    for ci in champ_items:
        item_prior[ci["item_id"]] = (ci["wins"] + K * champ_prior) / (ci["games"] + K)

    out = []
    for r in rows:
        prior = item_prior.get(r["item_id"], champ_prior)
        shrunk = (r["wins"] + K * prior) / (r["games"] + K)
        raw = r["wins"] / r["games"]
        out.append({
            "item": r["item_name"],
            "item_id": r["item_id"],
            "games": r["games"],
            "raw_winrate": round(raw, 3),
            "shrunk_winrate": round(shrunk, 3),
            "edge": round(shrunk - prior, 3),
        })
    out.sort(key=lambda x: x["edge"], reverse=True)
    return {"champion": champion, "opponent": opponent, "lane": lane,
            "version": ddragon_version(), "items": out}


def claude():
    global _anthropic
    if _anthropic is None:
        _anthropic = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _anthropic


@app.get("/explain")
def explain(champion: str, opponent: str, lane: str):
    """Natural-language coaching summary grounded in the computed stats."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Explanation feature not configured")
    lane = lane.upper()
 
    m = query(
        "SELECT games, wins FROM matchup_stats "
        "WHERE champion=%s AND opponent=%s AND lane=%s",
        (champion, opponent, lane),
    )
    if not m:
        raise HTTPException(404, "No data for that matchup")
    base = query(
        "SELECT winrate FROM champion_lane_stats WHERE champion=%s AND lane=%s",
        (champion, lane),
    )
    prior = float(base[0]["winrate"]) if base else 0.5
    mr = m[0]
    pop_shrunk = (mr["wins"] + K * prior) / (mr["games"] + K)
 
    personal = query(
        "SELECT games, shrunk_winrate, population_winrate, edge "
        "FROM personal_matchup_stats WHERE champion=%s AND opponent=%s AND lane=%s",
        (champion, opponent, lane),
    )
 
    # champion-wide item prior (used by both item slices)
    ibase = query("SELECT sum(games) g, sum(wins) w FROM champion_lane_stats WHERE champion=%s", (champion,))
    iprior = float(ibase[0]["w"]) / float(ibase[0]["g"]) if ibase and ibase[0]["g"] else 0.5
 
    # champion-wide items (well-sampled)
    champ_items = query(
        "SELECT item_name, games, wins FROM item_stats WHERE champion=%s AND games >= 20",
        (champion,),
    )
    champ_scored = sorted(
        (((it["wins"] + K * iprior) / (it["games"] + K) - iprior, it["item_name"], it["games"]) for it in champ_items),
        reverse=True,
    )[:4]
 
    # matchup-specific items (small samples), shrunk toward each item's champion-wide rate
    champ_item_rate = {}
    for ci in query("SELECT item_id, games, wins FROM item_stats WHERE champion=%s", (champion,)):
        champ_item_rate[ci["item_id"]] = (ci["wins"] + K * iprior) / (ci["games"] + K)
    mu_items = query(
        "SELECT item_name, item_id, games, wins FROM matchup_item_stats "
        "WHERE champion=%s AND opponent=%s AND lane=%s AND games >= 3",
        (champion, opponent, lane),
    )
    mu_scored = []
    for it in mu_items:
        p = champ_item_rate.get(it["item_id"], iprior)
        s = (it["wins"] + K * p) / (it["games"] + K)
        mu_scored.append((round(s - p, 3), it["item_name"], it["games"]))
    mu_scored.sort(reverse=True)
    mu_scored = mu_scored[:4]
 
    facts = [
        f"Matchup: {champion} vs {opponent} in {lane}.",
        f"Population shrunk win rate for {champion}: {pop_shrunk:.1%} over {mr['games']} games.",
    ]
    if personal:
        p = personal[0]
        facts.append(
            f"This player's personal record: {float(p['shrunk_winrate']):.1%} shrunk win rate "
            f"over {p['games']} games vs population {float(p['population_winrate']):.1%} "
            f"(edge {float(p['edge']):+.1%})."
        )
    else:
        facts.append("This player has not played this matchup.")
    if champ_scored:
        facts.append(
            "Champion-wide highest-edge items (large samples, reliable): "
            + ", ".join(f"{name} ({edge:+.1%}, {g} games)" for edge, name, g in champ_scored)
        )
    if mu_scored:
        facts.append(
            f"Items that trend well specifically into {opponent} (SMALL samples, less certain): "
            + ", ".join(f"{name} ({edge:+.1%} vs general build, only {g} games)" for edge, name, g in mu_scored)
        )
    else:
        facts.append(f"Not enough matchup-specific item data vs {opponent} to say anything reliable.")
 
    prompt = (
        "You are a League of Legends coaching assistant. Using ONLY the statistics below, write a "
        "direct 3-4 sentence summary for the player. Cover: (1) how they perform in this matchup vs "
        "the baseline, (2) their most reliable item choices (the champion-wide, large-sample ones), "
        "and (3) any items that trend well specifically into this opponent. CRITICAL: when you cite "
        "a small-sample number, explicitly note it is based on few games and therefore uncertain. "
        "Distinguish reliable (large-sample) advice from speculative (small-sample) advice. Do NOT "
        "invent champion abilities, strategy, or any facts not in the statistics.\n\n" + "\n".join(facts)
    )
 
    msg = claude().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return {"explanation": text}


def run():
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()