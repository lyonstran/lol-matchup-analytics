# Turns the raw match files into the small JSON files the website reads.
# This replaces the old Athena queries, the Postgres tables and the FastAPI endpoints.
#
# Input:  data/raw/matches/*.json   (made by sync_raw.py)
# Output: web/public/data/index.json              champion list + build info
#         web/public/data/champions/<Id>.json     everything about one champion
#
# Usage: uv run python pipeline/build.py
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

import ddragon
from shrinkage import K, shrink, confidence, verdict

load_dotenv(find_dotenv())

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "matches"
OUT_DIR = REPO_ROOT / "web" / "public" / "data"

MY_PUUID = os.environ.get("MY_PUUID", "")

# smallest samples worth showing (same defaults the old API used)
MIN_ITEM_GAMES = 10           # champion-wide items
MIN_MATCHUP_ITEM_GAMES = 3    # items into one specific opponent


# ---------- small helpers ----------

def add_game(table, key, win):
    """Count one game, and one win if `win`, under `key` in a {key: {games, wins}} dict."""
    if key not in table:
        table[key] = {"games": 0, "wins": 0}
    table[key]["games"] += 1
    if win:
        table[key]["wins"] += 1


def r3(x):
    """Round to 3 decimals for the JSON output."""
    return round(x, 3)


def completed_item_ids(items_raw):
    """Finished items only: nothing builds out of them, 2000+ gold, purchasable."""
    completed = set()
    for item_id, meta in items_raw.items():
        gold = meta.get("gold", {})
        if meta.get("into"):
            continue
        if gold.get("total", 0) < 2000:
            continue
        if not gold.get("purchasable", True):
            continue
        completed.add(int(item_id))
    return completed


def lane_prior(baselines, champ, lane):
    """The champion's win rate in that lane, shrunk toward 0.5 (or 0.5 if we have none).

    A baseline is a win rate from a sample too, so it gets the same treatment as
    everything else. Unshrunk, a champion with 1 game in a lane got a 0% or 100%
    baseline, and every matchup for it in that lane was pulled toward that.
    """
    base = baselines.get((champ, lane))
    if base is None:
        return 0.5
    return shrink(base["wins"], base["games"], 0.5)


# ---------- step 1: count everything in one pass over the matches ----------

def count_matches(champ_id_by_key, completed):
    """Read every match file once and fill all the counting tables."""
    baselines = {}       # (champ, lane)                  -> games, wins
    matchups = {}        # (champ, opp, lane)             -> games, wins
    items = {}           # (champ, item_id)               -> games, wins
    matchup_items = {}   # (champ, opp, lane, item_id)    -> games, wins
    personal = {}        # (champ, opp, lane), your games -> games, wins
    match_count = 0
    first_game = None
    last_game = None

    for path in sorted(RAW_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            match = json.load(f)
        match_count += 1

        created = match["info"]["gameCreation"]
        if first_game is None or created < first_game:
            first_game = created
        if last_game is None or created > last_game:
            last_game = created

        # one simple record per player who had a lane
        players = []
        for p in match["info"]["participants"]:
            if p["teamPosition"] == "":
                continue
            # numeric championId -> Data Dragon id (e.g. 62 -> "MonkeyKing").
            # A champion newer than Data Dragon falls back to Riot's championName.
            champ = champ_id_by_key.get(p["championId"], p["championName"])
            finished = set()
            for slot in ["item0", "item1", "item2", "item3", "item4", "item5"]:
                if p[slot] in completed:
                    finished.add(p[slot])
            players.append({
                "champ": champ,
                "lane": p["teamPosition"],
                "team": p["teamId"],
                "win": p["win"],
                "puuid": p["puuid"],
                "items": finished,
            })

        for me in players:
            add_game(baselines, (me["champ"], me["lane"]), me["win"])
            for item_id in me["items"]:
                add_game(items, (me["champ"], item_id), me["win"])

            # lane opponent: same lane, other team
            for opp in players:
                if opp["lane"] != me["lane"] or opp["team"] == me["team"]:
                    continue
                key = (me["champ"], opp["champ"], me["lane"])
                add_game(matchups, key, me["win"])
                for item_id in me["items"]:
                    add_game(matchup_items, key + (item_id,), me["win"])
                if me["puuid"] == MY_PUUID:
                    add_game(personal, key, me["win"])

    print(f"  read {match_count} matches")
    return {
        "baselines": baselines,
        "matchups": matchups,
        "items": items,
        "matchup_items": matchup_items,
        "personal": personal,
        "match_count": match_count,
        "first_game": first_game,
        "last_game": last_game,
    }


# ---------- step 2: shrink and arrange everything per champion ----------

def empty_champion(champ_id, name):
    return {
        "id": champ_id,
        "name": name,
        "overall": None,
        "lanes": {},
        "matchups": {},
        "items": [],
        "matchup_items": {},
        "personal": {},
    }


def build_champion_files(counts, champions, item_names):
    """Return {champ_id: dict ready to save as that champion's JSON file}."""
    baselines = counts["baselines"]
    out = {}
    for champ_id, name in champions.items():
        out[champ_id] = empty_champion(champ_id, name)

    # lane baselines (the priors for matchups) and each champion's overall rate
    totals = {}
    for (champ, lane), c in baselines.items():
        if champ not in out:
            continue
        out[champ]["lanes"][lane] = {
            "games": c["games"], "wins": c["wins"], "winrate": r3(c["wins"] / c["games"]),
        }
        if champ not in totals:
            totals[champ] = {"games": 0, "wins": 0}
        totals[champ]["games"] += c["games"]
        totals[champ]["wins"] += c["wins"]

    # overall_rate is the prior for items, so it is shrunk toward 0.5 like lane baselines;
    # the JSON still shows the raw rate next to its game count
    overall_rate = {}
    for champ, c in totals.items():
        overall_rate[champ] = shrink(c["wins"], c["games"], 0.5)
        out[champ]["overall"] = {
            "games": c["games"], "wins": c["wins"], "winrate": r3(c["wins"] / c["games"]),
        }

    # population matchups, shrunk toward the champion's rate in that lane
    pop_shrunk = {}
    for (champ, opp, lane), c in counts["matchups"].items():
        if champ not in out:
            continue
        prior = lane_prior(baselines, champ, lane)
        shrunk = shrink(c["wins"], c["games"], prior)
        pop_shrunk[(champ, opp, lane)] = shrunk
        lane_table = out[champ]["matchups"].setdefault(lane, {})
        lane_table[opp] = {
            "games": c["games"],
            "wins": c["wins"],
            "raw_winrate": r3(c["wins"] / c["games"]),
            "prior": r3(prior),
            "shrunk_winrate": r3(shrunk),
            "confidence": confidence(c["games"]),
        }

    # champion-wide items, shrunk toward the champion's overall rate
    item_shrunk = {}
    for (champ, item_id), c in counts["items"].items():
        if champ not in out:
            continue
        prior = overall_rate.get(champ, 0.5)
        shrunk = shrink(c["wins"], c["games"], prior)
        item_shrunk[(champ, item_id)] = shrunk
        if c["games"] >= MIN_ITEM_GAMES:
            out[champ]["items"].append({
                "item_id": item_id,
                "item": item_names.get(item_id, str(item_id)),
                "games": c["games"],
                "raw_winrate": r3(c["wins"] / c["games"]),
                "shrunk_winrate": r3(shrunk),
                "edge": r3(shrunk - prior),
            })

    # items into one opponent, shrunk toward that item's champion-wide shrunk rate
    for (champ, opp, lane, item_id), c in counts["matchup_items"].items():
        if champ not in out or c["games"] < MIN_MATCHUP_ITEM_GAMES:
            continue
        prior = item_shrunk.get((champ, item_id), overall_rate.get(champ, 0.5))
        shrunk = shrink(c["wins"], c["games"], prior)
        lane_table = out[champ]["matchup_items"].setdefault(lane, {})
        opp_list = lane_table.setdefault(opp, [])
        opp_list.append({
            "item_id": item_id,
            "item": item_names.get(item_id, str(item_id)),
            "games": c["games"],
            "raw_winrate": r3(c["wins"] / c["games"]),
            "shrunk_winrate": r3(shrunk),
            "edge": r3(shrunk - prior),
        })

    # your games: shrunk toward the ALREADY-SHRUNK population matchup (the hierarchy)
    for (champ, opp, lane), c in counts["personal"].items():
        if champ not in out:
            continue
        prior = pop_shrunk.get((champ, opp, lane))
        if prior is None:
            prior = lane_prior(baselines, champ, lane)
        shrunk = shrink(c["wins"], c["games"], prior)
        edge = shrunk - prior
        lane_table = out[champ]["personal"].setdefault(lane, {})
        lane_table[opp] = {
            "games": c["games"],
            "wins": c["wins"],
            "raw_winrate": r3(c["wins"] / c["games"]),
            "population_winrate": r3(prior),
            "shrunk_winrate": r3(shrunk),
            "edge": r3(edge),
            "verdict": verdict(edge),
        }

    # best items first
    for champ in out:
        out[champ]["items"].sort(key=edge_of, reverse=True)
        for lane_table in out[champ]["matchup_items"].values():
            for opp_list in lane_table.values():
                opp_list.sort(key=edge_of, reverse=True)

    return out


def edge_of(item_row):
    """Sort key: an item row's edge."""
    return item_row["edge"]


def name_of(champion_row):
    """Sort key: a champion's display name."""
    return champion_row["name"]


# ---------- step 3: write the files ----------

def write_json(path, data):
    """Save compact JSON (no spaces) to keep the files small."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)


def to_date(ms):
    """Riot timestamps are milliseconds since 1970; turn one into YYYY-MM-DD."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main():
    if not MY_PUUID:
        print("  warning: MY_PUUID is not set, so 'Your history' will be empty")

    print("Fetching Data Dragon static data...")
    version = ddragon.get_latest_version()
    champs_raw = ddragon.get_champions(version)
    items_raw = ddragon.get_items(version)
    item_names = ddragon.build_item_id_map(items_raw)
    completed = completed_item_ids(items_raw)

    # Data Dragon "id" (MonkeyKing) is what we key on; "name" (Wukong) is what we show
    champions = {}
    champ_id_by_key = {}
    for c in champs_raw.values():
        champions[c["id"]] = c["name"]
        champ_id_by_key[int(c["key"])] = c["id"]
    print(f"  patch {version}: {len(champions)} champions, {len(completed)} completed items")

    print(f"Counting games in {RAW_DIR} ...")
    counts = count_matches(champ_id_by_key, completed)

    print("Shrinking and arranging per champion...")
    files = build_champion_files(counts, champions, item_names)

    print(f"Writing JSON to {OUT_DIR} ...")
    for champ_id, data in files.items():
        write_json(OUT_DIR / "champions" / f"{champ_id}.json", data)

    champion_list = []
    for champ_id, name in champions.items():
        champion_list.append({"id": champ_id, "name": name})
    champion_list.sort(key=name_of)

    index = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "ddragon_version": version,
        "k": K,
        "match_count": counts["match_count"],
        "first_game": to_date(counts["first_game"]),
        "last_game": to_date(counts["last_game"]),
        "champions": champion_list,
    }
    write_json(OUT_DIR / "index.json", index)

    print(f"Done: {len(files)} champion files, "
          f"{len(counts['matchups'])} matchup cells, "
          f"{len(counts['personal'])} personal cells.")


if __name__ == "__main__":
    main()
