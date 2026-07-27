CREATE TABLE IF NOT EXISTS matchup_stats (
    champion    TEXT         NOT NULL,
    opponent    TEXT         NOT NULL,
    lane        TEXT         NOT NULL,
    games       INTEGER      NOT NULL,
    wins        INTEGER      NOT NULL,
    winrate     NUMERIC(5,3) NOT NULL,
    PRIMARY KEY (champion, opponent, lane)
);

CREATE TABLE IF NOT EXISTS champion_lane_stats (
    champion    TEXT         NOT NULL,
    lane        TEXT         NOT NULL,
    games       INTEGER      NOT NULL,
    wins        INTEGER      NOT NULL,
    winrate     NUMERIC(5,3) NOT NULL,
    PRIMARY KEY (champion, lane)
);