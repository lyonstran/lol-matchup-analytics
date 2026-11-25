"""
Generate the README figures from the raw match files.
Run from the repo root:  uv run python notebooks/generate_figures.py
(needs data/raw/matches/, so run pipeline/sync_raw.py first)
Writes PNGs to docs/figures/ and prints the numbers the README quotes.
"""
from pathlib import Path

import matplotlib.pyplot as plt

# notebook_data.py sits next to this file and also puts pipeline/ on the import path
from notebook_data import load_tables, load_lane_games
from backtest import random_match_split, backtest

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# colors (light chart surface): one data color plus text inks
DATA_BLUE = "#2a78d6"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#d9d8d4"

tables = load_tables()
matchups = tables["matchups"]
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

# --- Figure 2: the funnel: win rate vs sample size ---
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

# --- Figure 3: the backtest: each version of the site vs always guessing 50% ---
lane_games = load_lane_games()
train, test = random_match_split(lane_games)
results = backtest(train, test).set_index("estimator")

# (row name in the backtest, label on the chart), top to bottom
SITE_VERSIONS = [
    ("site before Nov 25: raw baseline, K=20", "Before: raw lane baselines, K = 20"),
    ("site step 3a: shrunk baseline, K=20", "Fix 1: shrunk lane baselines, K = 20"),
    ("site now: fitted k", "Fix 2: k fitted from the data"),
]

fig, ax = plt.subplots(figsize=(8, 3.6))
for row, (name, label) in enumerate(SITE_VERSIONS):
    y = len(SITE_VERSIONS) - 1 - row          # first entry at the top
    value = results.loc[name, "vs_coin_flip"]
    band = results.loc[name, "plus_minus_2se"]
    ax.errorbar(value, y, xerr=band, fmt="o", color=DATA_BLUE, markersize=8,
                elinewidth=2, capsize=4, capthick=2)
    ax.annotate(f"{value:+.4f} ± {band:.4f}", xy=(value + band, y), xytext=(8, 0),
                textcoords="offset points", va="center", fontsize=10, color=INK)

# the coin flip is the zero line
ax.axvline(0, color=INK_SOFT, ls="--", lw=1)
ax.annotate("always guess 50%", xy=(0, len(SITE_VERSIONS) - 0.45), xytext=(4, 0),
            textcoords="offset points", fontsize=9, color=INK_SOFT)

ax.set_yticks(range(len(SITE_VERSIONS)))
ax.set_yticklabels([label for _, label in reversed(SITE_VERSIONS)], fontsize=10, color=INK)
ax.set_ylim(-0.6, len(SITE_VERSIONS) - 0.3)
right_edge = results.loc[SITE_VERSIONS[0][0], "vs_coin_flip"] + results.loc[SITE_VERSIONS[0][0], "plus_minus_2se"]
ax.set_xlim(-0.01, right_edge * 1.45)
ax.set_xlabel("out-of-sample log loss minus always-50%'s  (right = worse, error bars = ±2 SE)",
              fontsize=9, color=INK_SOFT)
ax.set_title(f"Backtest on {test['match_id'].nunique():,} held-out matches", fontsize=12, color=INK)
ax.grid(axis="x", color=GRID, lw=0.8)
ax.set_axisbelow(True)
for side in ["top", "right", "left"]:
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(axis="x", colors=INK_SOFT, labelsize=9)
ax.tick_params(axis="y", length=0)
fig.tight_layout()
fig.savefig(OUT / "backtest.png", dpi=140)
plt.close(fig)

# the numbers the README quotes, so they can be checked against this run
print(f"\n{tables['match_count']} matches, {len(matchups)} matchup cells, "
      f"{(matchups['games'] == 1).sum()} with 1 game, {(matchups['games'] == 2).sum()} with 2")
print(f"backtest: {len(train)} train rows, {len(test)} test rows "
      f"({test['match_id'].nunique()} held-out matches)")
print(results.to_string())
print(f"\nWrote 3 figures to {OUT}")
