# Loads the match data for the notebook and the README figures.
#
# v1 read these tables out of Postgres. v2 has no database, so this file runs the
# same counting code the website build uses (pipeline/build.py) over the raw
# match files in data/raw/matches/, and turns the results into pandas tables.
# Because it reuses build.py, the notebook and the live site always agree.
#
# Usage (from a notebook or a script in this folder):
#     from notebook_data import load_tables
#     tables = load_tables()
#     matchups = tables["matchups"]
import sys
from pathlib import Path

import pandas as pd

# let Python find the pipeline scripts (build.py, ddragon.py, shrinkage.py)
REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = REPO_ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import build     # noqa: E402  (has to come after the sys.path line above)
import ddragon   # noqa: E402


def counts_to_frame(table, key_columns):
    """Turn a {key: {games, wins}} dict from build.py into a DataFrame.

    key_columns names the parts of each key, for example
    ["champion", "opponent", "lane"] for the matchup table.
    """
    rows = []
    for key, counts in table.items():
        # a key with one part (rare) still needs to behave like a tuple
        if not isinstance(key, tuple):
            key = (key,)
        row = {}
        for name, value in zip(key_columns, key):
            row[name] = value
        row["games"] = counts["games"]
        row["wins"] = counts["wins"]
        rows.append(row)
    return pd.DataFrame(rows, columns=key_columns + ["games", "wins"])


def load_tables():
    """Count every raw match and return the tables the notebook needs.

    Returns a dict of DataFrames:
      matchups   champion, opponent, lane, games, wins
      baselines  champion, lane, games, wins
      items      champion, item_id, item_name, games, wins   (finished items only)
      personal   champion, opponent, lane, games, wins       (your games, from MY_PUUID)
    plus "match_count" and "ddragon_version".
    """
    # Data Dragon: champion ids and the list of finished items, same as build.py
    version = ddragon.get_latest_version()
    champs_raw = ddragon.get_champions(version)
    items_raw = ddragon.get_items(version)
    item_names = ddragon.build_item_id_map(items_raw)
    completed = build.completed_item_ids(items_raw)

    champ_id_by_key = {}
    for c in champs_raw.values():
        champ_id_by_key[int(c["key"])] = c["id"]

    # one pass over every match file (takes a little while)
    counts = build.count_matches(champ_id_by_key, completed)

    matchups = counts_to_frame(counts["matchups"], ["champion", "opponent", "lane"])
    baselines = counts_to_frame(counts["baselines"], ["champion", "lane"])
    personal = counts_to_frame(counts["personal"], ["champion", "opponent", "lane"])

    items = counts_to_frame(counts["items"], ["champion", "item_id"])
    # add the item's display name next to its numeric id
    names = []
    for item_id in items["item_id"]:
        names.append(item_names.get(item_id, str(item_id)))
    items.insert(2, "item_name", names)

    if len(personal) == 0:
        print("note: no personal games found; is MY_PUUID set in your .env?")

    return {
        "matchups": matchups,
        "baselines": baselines,
        "items": items,
        "personal": personal,
        "match_count": counts["match_count"],
        "ddragon_version": version,
    }
