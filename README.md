# LoL Matchup Analytics

**Personalized League of Legends matchup analytics, powered by hierarchical Bayesian shrinkage.**

**Live site:** [lyonstran.github.io/lol-matchup-analytics](https://lyonstran.github.io/lol-matchup-analytics/), refreshed with new matches every day.

Most stat trackers report raw win rates on tiny samples, i.e., a "100% win rate" that's really 1 game. This tool builds population-level baselines from a corpus of ranked matches, then corrects individual matchup estimates toward those baselines using empirical-Bayes shrinkage, weighted by how much data actually backs each number. Every figure the tool shows comes with its sample size and a confidence label, because an honest estimate that says "we don't know yet" beats a confident lie.

> The core question this answers that op.gg can't: **"Do *I* actually beat the field in this matchup, and how sure can we be?"**

![Matchup analytics UI](docs/screenshot.png)
![Shrinkage chart and item recommendations](docs/screenshot2.png)

---

## Population data vs. your data

The tool draws on two distinct layers, and every panel in the UI is labeled by which one it uses:

| Panel | Data source | What it answers |
|-------|-------------|-----------------|
| **Matchup win rate** (top card, with confidence badge) | **Population** — the full corpus of crawled ranked matches | How this champion-vs-champion matchup goes *across all players*, shrunk for sample size |
| **Your history** (personal-vs-population card) | **Personal** — only matches containing the tracked player's PUUID | How *you specifically* perform in this matchup, and whether you beat the population baseline |
| **Top items for [champion]** | **Population** | Champion-wide item win rates across all players, ranked by shrunk edge |
| **Items vs [opponent]** | **Population** | Item win rates for this champion *into this specific opponent*, across all players |
| **Shrinkage chart** | **Population** | Raw vs. corrected item win rates, visualizing the shrinkage |
| **AI coaching summary** | **Both** | A plain-language summary that combines your personal edge with population item trends, flagging small samples |

The design principle is that **population data provides the priors and personal data is the signal being estimated**. Your personal history is small and noisy on its own — the population layer is what makes an honest personalized estimate possible. The "Your history" card is the only place your own games directly drive the numbers; everything else is population-wide context, and the AI summary is the one place the two are woven together.


---

## Why this is different

A player's personal history is *small data*. Over six games against a champion, a 4–2 record is statistically meaningless, essentially indistinguishable from a coin flip. Existing trackers report that 4–2 as "67%."

This project treats each sparse estimate as a **Bayesian update** on a population prior:

- Build champion-vs-champion matchup baselines from a large corpus of ranked matches.
- For any specific (and usually sparse) matchup, shrink the raw win rate toward that baseline, weighted by sample size. A 1-game "100%" collapses to the baseline; a 40-game rate barely moves.
- Apply the correction **hierarchically**: a player's personal cells shrink toward the *already-shrunk* population estimate, which itself shrinks toward the champion's overall lane rate. Priors shrink toward priors — the correct treatment for a long-tailed matchup space.

The shrinkage is validated with an out-of-sample backtest, not just asserted (see [The statistics](#the-statistics)).

---

## The statistics

The whole idea in one line: a win rate from a handful of games is mostly noise, so we pull it toward a trustworthy average, and we pull harder when we have less data.

### The problem

The obvious way to rate a matchup is wins divided by games. Call it $\hat{p} = w/n$. The trouble is how much that number bounces around when $n$ is small:

$$\mathrm{Var}(\hat{p}) = \frac{p(1-p)}{n}.$$

As $n$ shrinks, the variance blows up. At a single game the estimate is always exactly 0 or 1, maximally confident and completely useless. And most of the data looks like this. The vast majority of matchups have only one or two games behind them:

![Sparsity histogram](docs/figures/sparsity_histogram.png)

The same story from another angle. At low game counts the win rate is scattered everywhere, and it only settles down as games pile up:

![Win rate vs sample size](docs/figures/winrate_funnel.png)

That fan of noise on the left is exactly what the method fixes.

### The fix: shrinkage

Treat each matchup's wins as a Binomial draw, $w \sim \mathrm{Binomial}(n, p)$, and put a Beta prior on the true win rate $p$, centered on a baseline $\mu$ we already trust (the champion's overall rate in that lane):

$$p \sim \mathrm{Beta}(\alpha, \beta), \qquad \alpha = k\mu, \qquad \beta = k(1-\mu).$$

Here $\mu$ is where the prior is centered and $k$ is how strongly we believe it, measured in "pretend games." Because the Beta and Binomial fit together neatly, the updated (posterior) distribution is just another Beta:

$$p \mid w \sim \mathrm{Beta}(w + \alpha,\ n - w + \beta),$$

and its mean, which is the corrected win rate, turns out to be a simple weighted average of the data and the baseline:

$$\hat{p}_{\text{shrunk}} = \frac{w + k\mu}{n + k} = \frac{n}{n+k}\hat{p} + \frac{k}{n+k}\mu.$$

Read the two weights and the behavior is obvious. When you have lots of games, $n$ dominates, the weight lands on your actual win rate, and the estimate barely moves. When you have almost no games, $k$ dominates, the weight lands on the baseline, and the noisy number gets pulled home. There is no hard cutoff anywhere, and the transition is smooth as games accumulate.

![Raw vs shrunk win rate](docs/figures/raw_vs_shrunk.png)

Points off the diagonal are the ones shrinkage moved. The matchups with barely any games (dark) get yanked toward the baseline, while the ones with plenty of games (bright) sit on the line, barely touched. That is the entire method in one picture.

### Picking how strong the prior should be

The one real choice is $k$. Rather than guess it, we read it off the data, which is what makes this *empirical* Bayes rather than plain Bayes. Look at the matchups that actually have enough games to trust, see how spread out their win rates are, match that spread to the Beta, and solve:

$$\hat{k} = \frac{\bar{p}(1-\bar{p})}{s^2} - 1.$$

The intuition: if real matchups all sit close to the baseline (small spread), then extreme results are almost certainly luck, so the prior should be strong and $k$ large. If real matchups genuinely differ a lot (wide spread), the prior should be weaker.

### Priors leaning on priors

The baselines are themselves shrunk, which is what makes the whole thing hierarchical. Your personal win rate in a matchup leans on the population's (already corrected) win rate for that matchup, which leans on the champion's overall rate in the lane, which leans on a coin flip:

$$\hat{p}_{\text{personal}} \leftarrow \hat{p}_{\text{population}} \leftarrow \mu_{\text{lane}} \leftarrow 0.5.$$

Why this matters: if your personal matchup has three games and you lean it on a population cell that also has three games, you have just propped one noisy number against another. Leaning on the *corrected* population number instead gives it something solid underneath. In practice this visibly changed the personal estimates.

### Does it actually work?

Shrinkage is only worth anything if it predicts better on games it has not seen. So split the games into two halves, fit both estimators on the first half, and score them on the second half using log loss:

$$\text{log loss} = -\frac{1}{N}\sum_i \left[ y_i \log \hat{p}_i + (1-y_i)\log(1-\hat{p}_i) \right].$$

| Estimator | Out of sample log loss (lower is better) |
|-----------|------------------------------------------|
| Raw win rate | **3.68** |
| Bayesian shrunk | **0.69** |

Log loss comes down hard on being confidently wrong, which is exactly the raw estimator's failure mode: it calls a matchup 0% or 100% off a game or two, then reality disagrees in the test half. The shrunk estimator never claims more certainty than the data supports, so it lands right near the honest floor of $-\ln(0.5) \approx 0.693$, the score you get by sensibly saying "close to a coin flip" when you do not know.

To be precise about what this shows: shrinkage removes the overconfident small-sample errors, but a score of 0.69 is also what you get by always predicting 50%, so this backtest does not yet show that the shrunk estimates beat a coin flip. The next step is to add a constant 0.5 baseline and a lane-baseline-only estimator to the comparison, and to split the test by match rather than by games rebuilt from totals.

**Corpus:** about 3,800 ranked matches as of November 2026 (growing daily; the site footer shows the live count), giving roughly 12,900 matchup cells (one champion against another in a given lane), plus a personal layer of my own ranked games.

---

## Architecture

```mermaid
flowchart LR
    Riot["Riot Match-V5 API"] -->|"rate-limited crawler"| S3["S3 raw layer: immutable match JSON"]
    S3 -->|"sync new files"| Build["Python build: count, shrink, write JSON"]
    DDragon["Data Dragon static data"] --> Build
    Build --> Site["Static React site on GitHub Pages"]
    Claude["Anthropic API: optional coaching"] --> Site
    User["Player"] --> Site
```

Everything on the left runs once a day in GitHub Actions. The site itself is just files: there is no server and no database to keep running.

**How it fits together, step by step:**

1. **Collect the data.** A crawler pulls ranked matches from Riot's API. Riot enforces strict rate limits, so it throttles itself and walks outward from one player to the people in their games, then the people in *their* games, snowballing a large, varied corpus. Every raw match lands in S3 exactly as Riot returned it and is never modified, so the original data is always there to reprocess.

2. **Count and correct.** A plain Python build step reads every match once and counts games and wins for each champion in each lane, each champion-vs-champion matchup, each item, and each of my own games. It then applies the Bayesian shrinkage, the core of the project, turning noisy small-sample win rates into honest estimates.

3. **Publish precomputed answers.** The build writes one small JSON file per champion (a few MB in total). The React frontend loads only the file it needs, so every lookup is instant. Nothing is computed or fetched from Riot when someone uses the site.

4. **Explain it in plain English (optional).** The site can send the computed numbers to Claude, which writes a short coaching summary. Claude only ever sees the real statistics and is told to flag numbers based on too few games. This runs in the browser with the visitor's own Anthropic API key, so the site still needs no server.

In short: **raw matches in S3, then a daily Python build that counts and shrinks, then static JSON and a React site on GitHub Pages**, with an optional AI layer that turns the stats into advice.

### Why it is built this way

The first version (tag `v1-render`) used AWS Athena for SQL over S3, a Postgres feature store on Neon, a FastAPI service and a static site on Render, all wired together with Docker Compose. It worked, but every number it served changes at most once a day, the data the site needs is a few MB, and it has one user. The v2 rewrite precomputes everything in one daily job and serves plain files instead. That removed four hosted services, the cold starts of a free-tier API, and an Athena table that only existed in the AWS console, while producing the same numbers (checked value by value against the old API before switching over).

---

## The pipeline

| Stage | What it does | Key engineering |
|-------|--------------|-----------------|
| **Ingestion** | Crawls ranked matches into an immutable S3 raw layer | Dual sliding-window rate limiter (20/s + 100/2min), 429 backoff, dedup against a local copy, breadth-first player-graph crawl seeded from a permanent PUUID |
| **Storage** | Raw match JSON, never mutated or re-fetched | S3 with a least-privilege IAM key (no delete permission, enforcing immutability) |
| **Processing** | Matchup matrix, champion/lane baselines, item stats, matchup-specific items, personal record | One pass over the raw JSON in plain Python; champions keyed by numeric ID so renamed or oddly spelled champions always match |
| **Modeling** | Empirical-Bayes Beta-Binomial shrinkage | Hierarchical (personal, then population, then lane baseline); prior strength studied by method of moments in the notebook |
| **Publishing** | Precomputed estimates as static JSON | Daily GitHub Actions job: crawl, build, then deploy to GitHub Pages; raw matches cached between runs |
| **UI** | Matchup tool foregrounding confidence | React (Vite); sample size and confidence badges, item icons, a raw-vs-shrunk chart (Recharts), and grounded AI coaching summaries |

---

## Tech stack

**Data & cloud:** AWS S3, Riot Games API (production key), Data Dragon

**Pipeline:** Python, httpx, boto3, uv

**Modeling:** empirical-Bayes Beta-Binomial shrinkage (pandas, numpy, scipy in the notebook)

**AI:** Anthropic API (Claude) for grounded natural-language coaching summaries

**Frontend:** React, Vite, Recharts

**Automation & hosting:** GitHub Actions (daily refresh), GitHub Pages

---

## Running locally

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Node.js, an AWS account with an S3 bucket, a Riot API key, and (optional, for coaching summaries) an Anthropic API key.

```bash
# 1. Clone and configure
git clone https://github.com/lyonstran/lol-matchup-analytics.git
cd lol-matchup-analytics
cp .env.example .env          # fill in RIOT_API_KEY, AWS keys, S3_BUCKET, MY_PUUID
uv sync

# 2. Get the data
uv run python pipeline/sync_raw.py         # download raw matches from S3 into data/raw/matches
uv run python pipeline/crawl.py            # optional: crawl new matches (rate-limited)
uv run python pipeline/crawl_personal.py   # optional: crawl your own new matches

# 3. Build the site data
uv run python pipeline/build.py            # writes web/public/data/*.json

# 4. Run the site
cd web && npm install && npm run dev       # http://localhost:5173
```

`uv run python pipeline/lookup_puuid.py "<game name>" "<tag>"` prints the PUUID for a Riot ID.

---

## Project structure

```
lol-matchup-analytics/
├── pipeline/                   # all the Python
│   ├── crawl.py                # rate-limited breadth-first crawler, Riot to S3
│   ├── crawl_personal.py       # pages through my own ranked history
│   ├── sync_raw.py             # S3 to a local copy in data/raw/matches
│   ├── build.py                # counts, shrinks, writes the site's JSON
│   ├── shrinkage.py            # the Beta-Binomial shrinkage estimator
│   ├── riot_client.py          # Riot API client (retries, 429 handling)
│   ├── rate_limiter.py         # multi-window sliding rate limiter
│   └── s3.py, ddragon.py, config.py, lookup_puuid.py
├── web/                        # React (Vite) frontend
├── notebooks/                  # shrinkage prototype, backtest, EDA figures (still read the v1 tables; being ported)
├── docs/figures/               # figures used in this README
└── .github/workflows/          # daily refresh and deploy
```

---

## Author

**Lyons Tran** — Statistics @ UIUC (Minor in Data Science)
[Portfolio](https://lyonstran.github.io/) · [LinkedIn](https://www.linkedin.com/in/lyonstranuiuc/)

---

## Resources & further reading

The statistical methods in this project rest on standard Bayesian estimation theory. The two texts below were the primary references; specific sections are noted since they map directly onto the model.

### Statistics & Bayesian inference

- **Hogg, R. V., McKean, J. W. & Craig, A. T.** — *Introduction to Mathematical Statistics*, 7th ed. (Pearson).
  Course text for Bayesian inference. The shrinkage estimator used here is exactly the Bayesian point estimate derived in **11.2.2 (Bayesian Point Estimation, p. 612)**: a Beta prior on a Binomial proportion yields a Beta posterior, and the posterior mean $(\alpha + y)/(\alpha + \beta + n)$ *is* the shrunk win-rate estimate. Conjugacy of the Beta–Binomial family is formalized in **11.3 (p. 619)**, and the hierarchical/empirical-Bayes extension — priors informed by the data, the basis for shrinking personal rates toward population priors — is **11.5.1 (Empirical Bayes, p. 636)**.

- **Hogg, R. V., Tanis, E. A. & Zimmerman, D. L.** — *Probability and Statistical Inference*, 10th ed. (Pearson).
  Probability foundations and estimation. The Binomial distribution (**2.4, p. 63**) is the model for match outcomes; **Chapter 6 (Point Estimation, p. 233)** covers method-of-moments estimation (**p. 264**), used to fit the prior strength $k$ from the spread of well-sampled matchups; and **6.8 (Bayesian Estimation, p. 298)** develops the Beta–Binomial posterior directly.

### Documentation & tools

- [Riot Games API documentation](https://developer.riotgames.com/) — Match-V5, Account-V1, and rate-limit policy.
- [uv documentation](https://docs.astral.sh/uv/): Python environments and lockfile.
- [GitHub Actions](https://docs.github.com/en/actions) and [GitHub Pages](https://docs.github.com/en/pages): the daily refresh and hosting.

### Acknowledgments

- **Claude (Anthropic)** was used as a research and debugging aid throughout development, as well as talking through the statistical approach, working through implementation issues, and reviewing design decisions. All modeling choices, code, and the final implementation are my own.

---