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

CREATE TABLE IF NOT EXISTS item_stats (
    champion    TEXT         NOT NULL,
    item_id     INTEGER      NOT NULL,
    item_name   TEXT         NOT NULL,
    games       INTEGER      NOT NULL,
    wins        INTEGER      NOT NULL,
    winrate     NUMERIC(5,3) NOT NULL,
    PRIMARY KEY (champion, item_id)
);

CREATE TABLE IF NOT EXISTS personal_matchup_stats (
    champion    TEXT         NOT NULL,
    opponent    TEXT         NOT NULL,
    lane        TEXT         NOT NULL,
    games       INTEGER      NOT NULL,
    wins        INTEGER      NOT NULL,
    raw_winrate     NUMERIC(5,3) NOT NULL,
    population_winrate NUMERIC(5,3) NOT NULL,
    shrunk_winrate  NUMERIC(5,3) NOT NULL,
    edge            NUMERIC(6,3) NOT NULL,
    PRIMARY KEY (champion, opponent, lane)
);

CREATE TABLE IF NOT EXISTS matchup_item_stats (
    champion    TEXT         NOT NULL,
    opponent    TEXT         NOT NULL,
    lane        TEXT         NOT NULL,
    item_id     INTEGER      NOT NULL,
    item_name   TEXT         NOT NULL,
    games       INTEGER      NOT NULL,
    wins        INTEGER      NOT NULL,
    PRIMARY KEY (champion, opponent, lane, item_id)
);