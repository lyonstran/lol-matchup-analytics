# The empirical-Bayes (Beta-Binomial) shrinkage used everywhere in this project.
#
# Put a Beta(k * prior, k * (1 - prior)) prior on a true win rate, observe
# `wins` out of `games`, and the posterior mean is:
#
#     (wins + k * prior) / (games + k)
#
# k is how strongly we trust the prior, measured in "pretend games".
from math import lgamma

# k for the personal layer and items, where we have no good way to fit it yet
K = 20.0

# fitted k values are searched on this grid; the last value is the cap
K_GRID = [1, 2, 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000]

# a personal edge has to clear 3 percentage points to count as real
EDGE_THRESHOLD = 0.03


def shrink(wins, games, prior, k=K):
    """Pull a raw win rate toward `prior`; the fewer the games, the harder the pull."""
    return (wins + k * prior) / (games + k)


def beta_binomial_log_likelihood(cells, k):
    """How well a prior of strength k explains the data (higher is better).

    cells is a list of (wins, games, prior). For one cell the chance of seeing
    `wins` out of `games`, when the true rate is drawn from
    Beta(a, b) with a = k * prior and b = k * (1 - prior), is (up to a constant
    that doesn't depend on k):

        B(wins + a, losses + b) / B(a, b)

    where B is the Beta function. We add up the log of that over every cell,
    writing log B(x, y) as lgamma(x) + lgamma(y) - lgamma(x + y).
    """
    total = 0.0
    for wins, games, prior in cells:
        losses = games - wins
        a = k * prior
        b = k * (1 - prior)
        log_b_posterior = lgamma(wins + a) + lgamma(losses + b) - lgamma(games + k)
        log_b_prior = lgamma(a) + lgamma(b) - lgamma(k)
        total += log_b_posterior - log_b_prior
    return total


def fit_k(cells):
    """Pick the k on K_GRID that explains the data best (empirical Bayes).

    Small k: the data says cells really differ from their priors.
    k at the cap: the data can't tell cells apart from their priors yet.
    """
    best_k = K_GRID[0]
    best_score = None
    for k in K_GRID:
        score = beta_binomial_log_likelihood(cells, k)
        if best_score is None or score > best_score:
            best_k = k
            best_score = score
    return float(best_k)


def confidence(games):
    """Label how much data backs a number."""
    if games >= 30:
        return "high"
    if games >= 10:
        return "medium"
    return "low"


def verdict(edge):
    """Plain-words reading of a personal edge vs the population."""
    if edge > EDGE_THRESHOLD:
        return "you outperform here"
    if edge < -EDGE_THRESHOLD:
        return "you underperform here"
    return "about average for you"
