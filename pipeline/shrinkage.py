# The empirical-Bayes (Beta-Binomial) shrinkage used everywhere in this project.
#
# Put a Beta(K * prior, K * (1 - prior)) prior on a true win rate, observe
# `wins` out of `games`, and the posterior mean is:
#
#     (wins + K * prior) / (games + K)
#
# K is how strongly we trust the prior, measured in "pretend games".
# 20 matches the notebook default.

K = 20.0

# a personal edge has to clear 3 percentage points to count as real
EDGE_THRESHOLD = 0.03


def shrink(wins, games, prior):
    """Pull a raw win rate toward `prior`; the fewer the games, the harder the pull."""
    return (wins + K * prior) / (games + K)


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
