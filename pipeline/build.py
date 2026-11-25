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
from shrinkage import K, K_GRID, shrink, fit_k, confidence, verdict

load_dotenv(find_dotenv())

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw" / "matches"
OUT_DIR = REPO_ROOT / "web" / "public" / "data"

MY_PUUID = os.environ.get("MY_PUUID", "")

# smallest samples worth showing (same defaults the old API used)
MIN_ITEM_GAMES = 10           # champion-wide items
MIN_MATCHUP_ITEM_GAMES = 3    # items into one specific opponent

# a game this short (in seconds) is a remake, not a real game
REMAKE_SECONDS = 300

# Items are compared only between similar games: same game-length bucket and same
# number of finished items. Bucket edges in minutes: under 20, 20-25, 25-30, 30-35, 35+.
LENGTH_BUCKET_EDGES = [20, 25, 30, 35]


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


def is_remake(match):
    """True for a remade game: ended by early surrender, or shorter than 5 minutes.

    Riot still marks one team as the winner of a remake, but nobody really played,
    so counting it would add a fake win and a fake loss to every table.
    """
    info = match["info"]
    if info["gameDuration"] < REMAKE_SECONDS:
        return True
    for p in info["participants"]:
        if p.get("gameEndedInEarlySurrender"):
            return True
    return False


def length_bucket(seconds):
    """Which game-length bucket a game falls in: 0 = under 20 min, ..., 4 = 35 min or more."""
    minutes = seconds / 60
    bucket = 0
    for edge in LENGTH_BUCKET_EDGES:
        if minutes >= edge:
            bucket += 1
    return bucket


def lane_prior(baselines, champ, lane, k_lane):
    """The champion's win rate in that lane, shrunk toward 0.5 (or 0.5 if we have none).

    A baseline is a win rate from a sample too, so it gets the same treatment as
    everything else. Unshrunk, a champion with 1 game in a lane got a 0% or 100%
    baseline, and every matchup for it in that lane was pulled toward that.
    k_lane is the fitted prior strength for lane baselines (see fit_prior_strengths).
    """
    base = baselines.get((champ, lane))
    if base is None:
        return 0.5
    return shrink(base["wins"], base["games"], 0.5, k_lane)


# ---------- step 1: count everything in one pass over the matches ----------

def count_matches(champ_id_by_key, completed):
    """Read every match file once and fill all the counting tables."""
    baselines = {}       # (champ, lane)                  -> games, wins
    matchups = {}        # (champ, opp, lane)             -> games, wins
    items = {}           # (champ, item_id)               -> games, wins
    matchup_items = {}   # (champ, opp, lane, item_id)    -> games, wins
    personal = {}        # (champ, opp, lane), your games -> games, wins

    # the same games split by "stratum" = (length bucket, number of finished items),
    # so items can be compared with similar games (see item_expectations)
    strata = {}               # (stratum)                             -> games, wins, all players
    champ_strata = {}         # (champ, stratum)                      -> games, wins
    item_strata = {}          # (champ, item_id, stratum)             -> games, wins
    matchup_item_strata = {}  # (champ, opp, lane, item_id, stratum)  -> games, wins

    match_count = 0
    remakes = 0
    first_game = None
    last_game = None

    for path in sorted(RAW_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            match = json.load(f)
        if is_remake(match):
            remakes += 1
            continue
        match_count += 1

        created = match["info"]["gameCreation"]
        if first_game is None or created < first_game:
            first_game = created
        if last_game is None or created > last_game:
            last_game = created

        bucket = length_bucket(match["info"]["gameDuration"])

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
                "stratum": (bucket, len(finished)),
            })

        for me in players:
            stratum = me["stratum"]
            add_game(baselines, (me["champ"], me["lane"]), me["win"])
            add_game(strata, stratum, me["win"])
            add_game(champ_strata, (me["champ"], stratum), me["win"])
            for item_id in me["items"]:
                add_game(items, (me["champ"], item_id), me["win"])
                add_game(item_strata, (me["champ"], item_id, stratum), me["win"])

            # lane opponent: same lane, other team
            for opp in players:
                if opp["lane"] != me["lane"] or opp["team"] == me["team"]:
                    continue
                key = (me["champ"], opp["champ"], me["lane"])
                add_game(matchups, key, me["win"])
                for item_id in me["items"]:
                    add_game(matchup_items, key + (item_id,), me["win"])
                    add_game(matchup_item_strata, key + (item_id, stratum), me["win"])
                if me["puuid"] == MY_PUUID:
                    add_game(personal, key, me["win"])

    print(f"  read {match_count} matches (skipped {remakes} remakes)")
    return {
        "baselines": baselines,
        "matchups": matchups,
        "items": items,
        "matchup_items": matchup_items,
        "personal": personal,
        "strata": strata,
        "champ_strata": champ_strata,
        "item_strata": item_strata,
        "matchup_item_strata": matchup_item_strata,
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


def fit_prior_strengths(counts):
    """Fit k for lane baselines and for matchups from the data (the "empirical" in empirical Bayes).

    Each level is fitted against the level above it:
      lane baselines: each champion-lane win rate vs 0.5
      matchups:       each matchup win rate vs its (shrunk) lane baseline
    """
    baselines = counts["baselines"]

    lane_cells = []
    for c in baselines.values():
        lane_cells.append((c["wins"], c["games"], 0.5))
    k_lane = fit_k(lane_cells)

    matchup_cells = []
    for (champ, opp, lane), c in counts["matchups"].items():
        prior = lane_prior(baselines, champ, lane, k_lane)
        matchup_cells.append((c["wins"], c["games"], prior))
    k_matchup = fit_k(matchup_cells)

    return k_lane, k_matchup


def clamp(p):
    """Keep a probability away from exactly 0 or 1."""
    return min(max(p, 0.01), 0.99)


def add_expected(table, stratum_rate):
    """Collapse {(..., stratum): games, wins} into {(...): games, wins, expected}.

    `expected` is how many wins we'd predict if every game won at the overall
    win rate of its stratum (same length bucket, same number of finished items).
    """
    out = {}
    for key, c in table.items():
        base = key[:-1]       # the key without the stratum on the end
        stratum = key[-1]
        if len(base) == 1:
            base = base[0]    # (champ,) -> champ
        if base not in out:
            out[base] = {"games": 0, "wins": 0, "expected": 0.0}
        out[base]["games"] += c["games"]
        out[base]["wins"] += c["wins"]
        out[base]["expected"] += c["games"] * stratum_rate[stratum]
    return out


def item_expectations(counts):
    """Everything the item tables need to compare items with similar games.

    Returns:
      champ_lift:  {champ: how much more often the champion wins than expected, overall}
                   (shrunk toward 0 with K, so a champion with 3 games gets almost none)
      items:       {(champ, item_id): games, wins, expected}
      matchup_items: {(champ, opp, lane, item_id): games, wins, expected}
    """
    # the win rate of ALL players in each stratum, e.g. 20-25 minutes with 4 finished items
    stratum_rate = {}
    for stratum, c in counts["strata"].items():
        stratum_rate[stratum] = c["wins"] / c["games"]

    champ_lift = {}
    for champ, c in add_expected(counts["champ_strata"], stratum_rate).items():
        champ_lift[champ] = (c["wins"] - c["expected"]) / (c["games"] + K)

    items = add_expected(counts["item_strata"], stratum_rate)
    matchup_items = add_expected(counts["matchup_item_strata"], stratum_rate)
    return champ_lift, items, matchup_items


def build_champion_files(counts, champions, item_names, k_lane, k_matchup):
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

    # each champion's overall record, shown on the site next to its game count
    for champ, c in totals.items():
        out[champ]["overall"] = {
            "games": c["games"], "wins": c["wins"], "winrate": r3(c["wins"] / c["games"]),
        }

    # population matchups, shrunk toward the champion's (shrunk) rate in that lane,
    # with the fitted strength k_matchup
    pop_shrunk = {}
    for (champ, opp, lane), c in counts["matchups"].items():
        if champ not in out:
            continue
        prior = lane_prior(baselines, champ, lane, k_lane)
        shrunk = shrink(c["wins"], c["games"], prior, k_matchup)
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

    # ----- items: compared with similar games, not with the champion's overall rate -----
    # Items come from the final inventory, and a player who finished more items in a
    # game of the same length was usually winning. So "games with this item" win more
    # than the champion's average almost no matter what the item is. Instead, each
    # item is compared with what we'd EXPECT in games of the same length with the same
    # number of finished items (see item_expectations).
    champ_lift, item_expected, matchup_item_expected = item_expectations(counts)

    # champion-wide items: prior = expected win rate for these games + the champion's lift
    item_lift = {}
    for (champ, item_id), c in item_expected.items():
        if champ not in out:
            continue
        expected_rate = c["expected"] / c["games"]
        prior = clamp(expected_rate + champ_lift.get(champ, 0.0))
        shrunk = shrink(c["wins"], c["games"], prior)
        # how far this item's games beat expectation, kept as the prior for matchup items
        item_lift[(champ, item_id)] = shrunk - expected_rate
        if c["games"] >= MIN_ITEM_GAMES:
            out[champ]["items"].append({
                "item_id": item_id,
                "item": item_names.get(item_id, str(item_id)),
                "games": c["games"],
                "raw_winrate": r3(c["wins"] / c["games"]),
                "shrunk_winrate": r3(shrunk),
                "edge": r3(shrunk - prior),
            })

    # items into one opponent: prior = expected win rate for these games + how much the
    # item beats expectation for this champion in general, so the edge says whether it
    # does even better (or worse) into this specific opponent
    for (champ, opp, lane, item_id), c in matchup_item_expected.items():
        if champ not in out or c["games"] < MIN_MATCHUP_ITEM_GAMES:
            continue
        expected_rate = c["expected"] / c["games"]
        lift = item_lift.get((champ, item_id), champ_lift.get(champ, 0.0))
        prior = clamp(expected_rate + lift)
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
            prior = lane_prior(baselines, champ, lane, k_lane)
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

    print("Fitting prior strengths...")
    k_lane, k_matchup = fit_prior_strengths(counts)
    print(f"  k for lane baselines: {k_lane:g}, k for matchups: {k_matchup:g} "
          f"(cap {K_GRID[-1]}); personal and items use {K:g}")

    print("Shrinking and arranging per champion...")
    files = build_champion_files(counts, champions, item_names, k_lane, k_matchup)

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
        "k": K,                   # personal layer and items
        "k_lane": k_lane,         # fitted: lane baselines toward 0.5
        "k_matchup": k_matchup,   # fitted: matchups toward their lane baseline
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
