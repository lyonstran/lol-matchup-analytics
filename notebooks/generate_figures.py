"""
Generate EDA figures for the README from the Postgres feature store.
Run from the repo root with the workspace venv:  uv run python notebooks/generate_figures.py
Writes PNGs to docs/figures/.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import psycopg
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

K = 20.0  # shrinkage prior strength

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    matchups = pd.read_sql("SELECT * FROM matchup_stats", conn)
    baselines = pd.read_sql("SELECT * FROM champion_lane_stats", conn)

matchups["games"] = matchups["games"].astype(int)
matchups["wins"] = matchups["wins"].astype(int)
matchups["raw"] = matchups["wins"] / matchups["games"]

# --- Figure 1: the sparsity histogram (the long tail) ---
counts = matchups["games"].value_counts().sort_index()
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.bar(counts.index[:25], counts.values[:25], color="#4285f4")
ax.set_xlabel("games in a matchup cell")
ax.set_ylabel("number of matchups")
ax.set_title("Most matchups are desperately sparse")
ax.annotate(f"{counts.iloc[0]:,} matchups\nwith just 1 game",
            xy=(1, counts.iloc[0]), xytext=(6, counts.iloc[0] * 0.8),
            arrowprops=dict(arrowstyle="->", color="#333"), fontsize=11)
fig.tight_layout()
fig.savefig(OUT / "sparsity_histogram.png", dpi=140)
plt.close(fig)

# --- Figure 2: the funnel — win rate vs sample size ---
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.scatter(matchups["games"], matchups["raw"], alpha=0.15, s=12, color="#4285f4")
ax.axhline(0.5, color="#f59e0b", ls="--", lw=1)
ax.set_xlabel("games")
ax.set_ylabel("raw win rate")
ax.set_title("Raw win rate vs. sample size (the funnel of noise)")
ax.set_xlim(0, matchups["games"].quantile(0.999))
fig.tight_layout()
fig.savefig(OUT / "winrate_funnel.png", dpi=140)
plt.close(fig)

# --- Figure 3: raw vs shrunk — the correction, colored by sample size ---
base_lookup = baselines.set_index(["champion", "lane"])["winrate"].astype(float)
matchups["mu"] = matchups.apply(
    lambda r: base_lookup.get((r["champion"], r["lane"]), 0.5), axis=1)
matchups["shrunk"] = (matchups["wins"] + K * matchups["mu"]) / (matchups["games"] + K)

fig, ax = plt.subplots(figsize=(7, 6))
sc = ax.scatter(matchups["raw"], matchups["shrunk"],
                c=np.log10(matchups["games"]), cmap="viridis", alpha=0.5, s=14)
ax.plot([0, 1], [0, 1], color="#999", ls="--", lw=1)  # y = x (no shrinkage)
ax.set_xlabel("raw win rate")
ax.set_ylabel("shrunk win rate")
ax.set_title("Shrinkage pulls extremes toward the baseline")
cbar = fig.colorbar(sc, ax=ax)
cbar.set_label("log10(games)")
fig.tight_layout()
fig.savefig(OUT / "raw_vs_shrunk.png", dpi=140)
plt.close(fig)

print(f"Wrote 3 figures to {OUT}")