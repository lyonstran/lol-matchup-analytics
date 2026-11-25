# The match-level backtest, shared by shrinkage.ipynb (section 4) and generate_figures.py.
#
# Fit each estimator on some matches, predict the win probability of every lane in
# the other matches, and score the predictions against "always guess 50%".
#
# Usage:
#     from notebook_data import load_lane_games
#     from backtest import random_match_split, backtest
#     train, test = random_match_split(load_lane_games())
#     results = backtest(train, test)
import numpy as np
import pandas as pd

import notebook_data  # noqa: F401  (puts pipeline/ on the import path)
import build
from shrinkage import K, fit_k


# ---------- splitting ----------

def random_match_split(lane_games, train_share=0.8, seed=42):
    """Shuffle the match ids; the first train_share of them train, the rest test.
    All rows of one match land on the same side, so no game is both learned and tested."""
    match_ids = pd.Series(lane_games["match_id"].unique())
    shuffled = match_ids.sample(frac=1, random_state=seed)
    cut = int(len(shuffled) * train_share)
    train_ids = set(shuffled.iloc[:cut])
    in_train = lane_games["match_id"].isin(train_ids)
    return lane_games[in_train], lane_games[~in_train]


def time_split(lane_games, train_share=0.8):
    """Train on the oldest train_share of matches, test on the newest."""
    match_times = lane_games.groupby("match_id")["game_creation"].first().sort_values()
    cut = int(len(match_times) * train_share)
    old_ids = set(match_times.index[:cut])
    is_old = lane_games["match_id"].isin(old_ids)
    return lane_games[is_old], lane_games[~is_old]


# ---------- the estimators ----------

def fit_counts(train):
    """Count games and wins per (champion, lane) and per matchup, from training rows only."""
    lane_counts = {}
    matchup_counts = {}
    for champ, opp, lane, win in zip(train["champion"], train["opponent"], train["lane"], train["win"]):
        build.add_game(lane_counts, (champ, lane), win)
        build.add_game(matchup_counts, (champ, opp, lane), win)
    return lane_counts, matchup_counts


def lane_rate(lane_counts, champ, lane, k_lane):
    """The champion's win rate in this lane, shrunk toward 0.5 with strength k_lane.
    k_lane = 0 means no shrinking (the raw rate). Never seen: 0.5."""
    c = lane_counts.get((champ, lane))
    if c is None:
        return 0.5
    return (c["wins"] + k_lane * 0.5) / (c["games"] + k_lane)


def matchup_rate(matchup_counts, champ, opp, lane, prior, k_matchup):
    """The matchup win rate, shrunk toward `prior` with strength k_matchup.
    k_matchup = 0 means the raw rate. Never seen: fall back to the prior."""
    c = matchup_counts.get((champ, opp, lane))
    if c is None:
        return prior
    return (c["wins"] + k_matchup * prior) / (c["games"] + k_matchup)


def predict(lane_counts, matchup_counts, champ, opp, lane, k_lane, k_matchup):
    """One estimator's win probability. None for a k means: skip that level."""
    # level 1: the prior for this champion in this lane
    if k_lane is None:
        prior = 0.5
    else:
        prior = lane_rate(lane_counts, champ, lane, k_lane)
    # level 2: the matchup, pulled toward that prior
    if k_matchup is None:
        return prior
    return matchup_rate(matchup_counts, champ, opp, lane, prior, k_matchup)


def fit_on_train(lane_counts, matchup_counts):
    """Fit k_lane and k_matchup on the training games only, the same way build.py does."""
    lane_cells = []
    for c in lane_counts.values():
        lane_cells.append((c["wins"], c["games"], 0.5))
    k_lane = fit_k(lane_cells)

    matchup_cells = []
    for (champ, opp, lane), c in matchup_counts.items():
        prior = lane_rate(lane_counts, champ, lane, k_lane)
        matchup_cells.append((c["wins"], c["games"], prior))
    k_matchup = fit_k(matchup_cells)
    return k_lane, k_matchup


# the estimators to compare: (name, k for the lane level, k for the matchup level)
# "fit" means: use the k fitted on the training games
ESTIMATORS = [
    ("constant 0.5",                             None,  None),
    ("lane baseline, raw",                       0,     None),
    ("lane baseline, shrunk (K=20)",             K,     None),
    ("matchup, raw",                             None,  0),
    ("site before Nov 25: raw baseline, K=20",   0,     K),
    ("site step 3a: shrunk baseline, K=20",      K,     K),
    ("site now: fitted k",                       "fit", "fit"),
]


# ---------- scoring ----------

def log_loss_each(y, p):
    """Log loss of every single prediction (clipped so 0% or 100% doesn't give infinity)."""
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def backtest(train, test):
    """Fit every estimator on `train`, score it on `test`, return one row per estimator.

    vs_coin_flip is the estimator's average log loss minus the coin flip's (negative =
    better). The 10 rows of one match share a result, so they aren't independent: the
    standard error is computed from per-match totals.
    """
    lane_counts, matchup_counts = fit_counts(train)
    fitted_lane, fitted_matchup = fit_on_train(lane_counts, matchup_counts)
    print(f"fitted on the training games: k_lane = {fitted_lane:g}, k_matchup = {fitted_matchup:g}")

    y = test["win"].to_numpy()
    coin_flip_loss = log_loss_each(y, np.full(len(y), 0.5))
    match_of_row = test["match_id"].to_numpy()
    n_matches = test["match_id"].nunique()

    results = []
    for name, k_lane, k_matchup in ESTIMATORS:
        if k_lane == "fit":
            k_lane = fitted_lane
        if k_matchup == "fit":
            k_matchup = fitted_matchup
        preds = []
        for champ, opp, lane in zip(test["champion"], test["opponent"], test["lane"]):
            preds.append(predict(lane_counts, matchup_counts, champ, opp, lane, k_lane, k_matchup))
        preds = np.array(preds)
        loss = log_loss_each(y, preds)

        # paired comparison with the coin flip, added up per match
        diff_per_match = pd.Series(loss - coin_flip_loss).groupby(match_of_row).sum()
        vs_coin_flip = diff_per_match.sum() / len(test)
        std_error = diff_per_match.std() * np.sqrt(n_matches) / len(test)

        results.append({
            "estimator": name,
            "log_loss": round(loss.mean(), 4),
            "brier": round(np.mean((preds - y) ** 2), 4),
            "vs_coin_flip": round(vs_coin_flip, 4),
            "plus_minus_2se": round(2 * std_error, 4),
        })
    return pd.DataFrame(results)
