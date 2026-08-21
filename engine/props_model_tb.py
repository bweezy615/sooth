"""Batter total-bases projection — our second prop model, built to be graded.

The strikeout model treats a start as Poisson around an expected rate. That
works because strikeouts are counts of one kind of event. Total bases are not:
a plate appearance returns 0, 1, 2, 3 or 4 bases, and the 4 is rare and huge.
Poisson on total bases would understate the variance badly, and an understated
variance manufactures confident-looking edges at exactly the lines we publish.

So this model builds the distribution the honest way — exactly, by convolution:

    per-PA outcome rates  ->  distribution of bases in one PA
    convolved n times     ->  distribution of bases in n plate appearances
    mixed over n          ->  distribution of bases in a game

Nothing is approximated. The support is small (a game is at most a handful of
PAs, each worth at most 4 bases), so the exact answer is cheap.

Two deliberate differences from the strikeout model, both documented because
they will look like omissions otherwise:

  - No recency weighting. The K model shrinks a last-5 rate toward the season
    rate, because a pitcher's stuff and workload really do drift within a
    season. Per-PA hitting rates do not drift that fast; what looks like a hot
    streak is mostly batted-ball luck that does not carry forward. Weighting
    recent games here would chase noise and call it form. Season rates only.

  - No opponent factor. Total bases are dominated by the opposing *starting
    pitcher*, not the opposing team. A team-level rate would be a weak proxy
    wearing the costume of a real adjustment, and unlike the K model's version
    it cannot be validated by the backtest (historical opponent strength
    as-of-date is not cheaply available). Left out until it can be graded.

Thin samples are handled by shrinking every rate toward league average with a
pseudo-count. The size of that pseudo-count is the one thing here that had to
be measured rather than reasoned out, and the first version got it badly wrong:
at 200 pseudo-PAs the model regressed good hitters most of the way to league
average and under-predicted the over by 2.8-3.3 points on exactly the hitters
props are posted on. Shrinkage toward a league mean is the wrong prior for a
population that is above the mean by selection. Now 25 pseudo-PAs, with a
25-game floor doing the stabilising instead.

Both numbers were chosen on a tuning sample (batters 41-100 by total bases)
and then validated once on a disjoint held-out sample (the top 40) so the
reported calibration is not the number they were fitted to.

    held-out, 3907 batter-games, 2026:
      line 1.5   predicted 43.3%   actual 44.4%   gap -1.1 pts
      line 2.5   predicted 27.7%   actual 29.0%   gap -1.3 pts

The residual is small but it is not noise-shaped: it leans the same way at
both lines, so this model still slightly under-states the over, which means it
slightly over-states any UNDER edge.

That aggregate number is the flattering one, and on its own it is misleading —
but not for the reason first written here. An earlier version of this note
claimed the problem was per-player error of about +-3.5 points, measured
in-sample. That was over-read: checked properly, walk-forward and with the
binomial sampling floor separated out, per-player deviation for BOTH this
model and kpoisson-v1 is entirely consistent with sampling noise. Per-player
calibration is not measurable at 100-150 games per batter, in either
direction. The real defect is elsewhere and it is sharper.

Bucket the walk-forward predictions by the probability the model assigned and
compare each bucket to what actually happened:

    line 1.5    p~0.2  predicted 27.3%   actual 40.4%    -13.1
                p~0.3  predicted 36.6%   actual 40.9%     -4.4
                p~0.4  predicted 44.0%   actual 42.0%     +2.1
                p~0.5  predicted 52.2%   actual 41.3%    +10.9

The overall gap across all of it is -0.5 points. The buckets are wrong by up
to thirteen. They cancel, which is the only reason the aggregate looks clean.

The shape is a compressed slope: every probability this model publishes is too
extreme, and the truth sits closer to the base rate than we say. kpoisson-v1
does the same thing at the same magnitude, so it is not a total-bases problem
and it is not a convolution problem.

The cause is NOT what was first written here. The first guess was plug-in
tail probabilities ignoring parameter uncertainty, with a negative-binomial /
Dirichlet-multinomial predictive as the fix. That was tested and it failed:
fitting the negative binomial to strikeouts gives r = 180, i.e. essentially no
over-dispersion (residual variance 5.49 against a Poisson 5.32), and it moved
the worst bucket only from 16.9 to 15.8 points. The variance family was never
the problem.

The defect is in the MEAN. Regressing actual outcomes on the projection,
held out, gives a slope well under one — 0.63 for strikeouts, 0.21 for total
bases. The projections move further than reality does, so every probability
derived from them is too extreme. For total bases a slope of 0.21 also says
something blunter: only about a fifth of this model's spread between batters
is real, and the rest is estimation noise dressed as discrimination.

Correcting the slope (fit on one half of players, validated on the other)
takes the worst bucket from 16.9 to 2.6 for strikeouts and 10.1 to 4.5 here.
That correction is NOT yet applied in this file, for a reason worth keeping:
it was validated at lines placed near the centre of each player's
distribution, and real board lines frequently sit in the tail, where tail
probabilities are far more sensitive to a shift in the mean. Applied to a live
board it produced double-digit under-edges on exactly the elite pitchers a
population-mean shrink would be expected to over-correct — the same
over-shrinking error this module already made once, in a new place. It needs
re-validating with lines where books actually hang them before it is used.

Why this matters more than the aggregate: delta_pts is what we publish against
the market, and the market prices close to the base rate. So our disagreements
with it are concentrated in exactly the buckets where we are most overconfident.
At p~0.5 above, the model says 52.2%, the market would say about 41%, and the
truth is 41.3%. That is an eleven-point "edge" that is entirely ours. Ranking
props by delta_pts therefore sorts by our own overconfidence, in every market,
until the predictive fix lands.

Everything comes from MLB's free StatsAPI.

    python -m engine.props_model_tb --backtest   # walk-forward accuracy report
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import requests

from .hitrates import API, find_player
from .props_model import over_threshold

MIN_GAMES = 25          # below this we do not project at all
SHRINK_PA = 25.0        # pseudo-PAs of league average mixed into every rate
PA_WINDOW = 25          # games used for the plate-appearance distribution
VERSION = "tbconv-v1"

# League per-PA fallbacks, used only if the league call fails. Roughly a
# league-average hitter: ~.245 avg with normal extra-base distribution.
LEAGUE_FALLBACK = {"s": 0.150, "d": 0.045, "t": 0.004, "hr": 0.032}


def batting_log(pid: int, season: int, session: requests.Session) -> list[dict]:
    """Per-game hitting line, oldest first. Games with no PA are dropped."""
    r = session.get(f"{API}/people/{pid}/stats",
                    params={"stats": "gameLog", "group": "hitting",
                            "season": season}, timeout=20)
    if r.status_code != 200:
        return []
    for s in r.json().get("stats", []):
        out = []
        for sp in s.get("splits", []):
            st = sp.get("stat", {})
            try:
                pa = float(st.get("plateAppearances"))
                h = float(st.get("hits"))
                d = float(st.get("doubles"))
                t = float(st.get("triples"))
                hr = float(st.get("homeRuns"))
                tb = float(st.get("totalBases"))
            except (TypeError, ValueError):
                continue
            if pa <= 0:
                continue
            single = h - d - t - hr
            if single < 0:               # malformed line; do not guess
                continue
            out.append({"pa": pa, "s": single, "d": d, "t": t, "hr": hr,
                        "tb": tb})
        return out
    return []


def league_batting_rates(season: int, session: requests.Session) -> dict:
    """League-wide per-PA rates for singles, doubles, triples, home runs."""
    r = session.get(f"{API}/teams/stats",
                    params={"season": season, "sportIds": 1,
                            "group": "hitting", "stats": "season"},
                    timeout=25)
    if r.status_code != 200:
        return dict(LEAGUE_FALLBACK)
    tot = {"pa": 0.0, "s": 0.0, "d": 0.0, "t": 0.0, "hr": 0.0}
    for s in r.json().get("stats", []):
        for sp in s.get("splits", []):
            st = sp.get("stat", {})
            try:
                pa = float(st.get("plateAppearances"))
                h = float(st.get("hits"))
                d = float(st.get("doubles"))
                t = float(st.get("triples"))
                hr = float(st.get("homeRuns"))
            except (TypeError, ValueError):
                continue
            if pa <= 0:
                continue
            tot["pa"] += pa
            tot["s"] += h - d - t - hr
            tot["d"] += d
            tot["t"] += t
            tot["hr"] += hr
    if tot["pa"] <= 0:
        return dict(LEAGUE_FALLBACK)
    return {k: tot[k] / tot["pa"] for k in ("s", "d", "t", "hr")}


def pa_pmf(log: list[dict]) -> dict:
    """Empirical distribution of plate appearances in a game.

    A projection that used mean PA would smear a batter who alternates 3 and 5
    into a phantom 4 every night. The spread matters at a 1.5 line, so keep the
    whole distribution rather than its average.
    """
    recent = log[-PA_WINDOW:]
    counts: dict = {}
    for g in recent:
        n = int(round(g["pa"]))
        if n <= 0:
            continue
        counts[n] = counts.get(n, 0) + 1
    total = sum(counts.values())
    if not total:
        return {}
    return {n: c / total for n, c in counts.items()}


def per_pa_rates(log: list[dict], league: dict,
                 shrink: float = SHRINK_PA) -> dict:
    """Season per-PA outcome rates, shrunk toward league by `shrink` PAs."""
    pa = sum(g["pa"] for g in log)
    if pa <= 0:
        return {}
    out = {}
    for key in ("s", "d", "t", "hr"):
        made = sum(g[key] for g in log)
        out[key] = (made + shrink * league[key]) / (pa + shrink)
    hit_rate = sum(out.values())
    if hit_rate >= 1.0:                  # cannot happen in practice; guard anyway
        return {}
    out["out"] = 1.0 - hit_rate
    return out


def bases_pmf(rates: dict) -> list[float]:
    """P(bases) for a single plate appearance, index = bases 0..4."""
    return [rates["out"], rates["s"], rates["d"], rates["t"], rates["hr"]]


def convolve(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        if ai == 0.0:
            continue
        for j, bj in enumerate(b):
            out[i + j] += ai * bj
    return out


def tb_pmf(rates: dict, pas: dict) -> list[float]:
    """Distribution of total bases in a game, mixed over the PA distribution."""
    one = bases_pmf(rates)
    by_n: dict = {}
    max_n = max(pas)
    cur = [1.0]                          # n = 0
    for n in range(1, max_n + 1):
        cur = convolve(cur, one)
        by_n[n] = cur
    size = max(len(v) for v in by_n.values())
    out = [0.0] * size
    for n, q in pas.items():
        dist = by_n.get(n)
        if not dist:
            continue
        for k, p in enumerate(dist):
            out[k] += q * p
    return out


def sf(pmf: list[float], k: int) -> float:
    """P(TB >= k)."""
    if k <= 0:
        return 1.0
    return max(0.0, min(1.0, sum(pmf[k:])))


def project(log: list[dict], league: dict,
            shrink: float = SHRINK_PA) -> dict | None:
    """Total-bases distribution for a game, from prior games only."""
    if len(log) < MIN_GAMES:
        return None                      # too thin to project honestly
    rates = per_pa_rates(log, league, shrink)
    pas = pa_pmf(log)
    if not rates or not pas:
        return None
    pmf = tb_pmf(rates, pas)
    exp_tb = sum(k * p for k, p in enumerate(pmf))
    exp_pa = sum(n * q for n, q in pas.items())
    return {"pmf": pmf, "exp_tb": exp_tb, "exp_pa": exp_pa, "rates": rates}


def backtest(season: int = 2026, min_games: int = MIN_GAMES,
             sample_batters: int = 40) -> dict:
    """Walk-forward accuracy on real games the model never saw.

    For every game i >= min_games of each sampled batter, project from games
    < i and score against the actual total bases. Two things are graded, and
    the second is the one that matters:

      - MAE against a season-to-date-mean baseline. Sanity only.
      - Calibration of P(over) at the lines we actually publish (1.5 and 2.5).
        We publish a probability next to the market's, so a model that is
        accurate on average but miscalibrated in the tails is still unfit.
        Brier score and a predicted-vs-realised comparison, published either
        way.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-props-model/1.0 (+https://sooth.bet)"
    league = league_batting_rates(season, session)

    r = session.get(f"{API}/stats/leaders",
                    params={"leaderCategories": "totalBases",
                            "statGroup": "hitting", "season": season,
                            "limit": sample_batters, "sportId": 1},
                    timeout=25)
    pids = []
    if r.status_code == 200:
        for cat in r.json().get("leagueLeaders", []):
            for l in cat.get("leaders", []):
                pid = (l.get("person") or {}).get("id")
                if pid:
                    pids.append(pid)
    pids = list(dict.fromkeys(pids))[:sample_batters]

    n = 0
    abs_err = base_err = 0.0
    lines = {1.5: {"p": 0.0, "hit": 0, "brier": 0.0, "n": 0},
             2.5: {"p": 0.0, "hit": 0, "brier": 0.0, "n": 0}}
    cover = 0

    for pid in pids:
        log = batting_log(pid, season, session)
        time.sleep(0.12)
        for i in range(min_games, len(log)):
            prior, actual = log[:i], log[i]["tb"]
            proj = project(prior, league)
            if not proj:
                continue
            n += 1
            abs_err += abs(proj["exp_tb"] - actual)
            base = sum(g["tb"] for g in prior) / len(prior)
            base_err += abs(base - actual)

            for line, acc in lines.items():
                need = over_threshold(line)
                p = sf(proj["pmf"], need)
                won = 1 if actual >= need else 0
                acc["p"] += p
                acc["hit"] += won
                acc["brier"] += (p - won) ** 2
                acc["n"] += 1

            # 80% central interval coverage, same check as the K model
            c = 0.0
            lo = hi = None
            for k, p in enumerate(proj["pmf"]):
                c += p
                if lo is None and c >= 0.10:
                    lo = k
                if hi is None and c >= 0.90:
                    hi = k
                    break
            if lo is not None and hi is not None and lo <= actual <= hi:
                cover += 1

    out = {"season": season, "version": VERSION, "batters": len(pids),
           "games_graded": n,
           "mae": round(abs_err / n, 3) if n else None,
           "baseline_season_mean_mae": round(base_err / n, 3) if n else None,
           "interval80_coverage_pct": round(cover / n * 100, 1) if n else None,
           "lines": {}}
    for line, acc in lines.items():
        if not acc["n"]:
            continue
        out["lines"][str(line)] = {
            "predicted_over_pct": round(acc["p"] / acc["n"] * 100, 1),
            "actual_over_pct": round(acc["hit"] / acc["n"] * 100, 1),
            "calibration_gap_pts": round(
                (acc["p"] / acc["n"] - acc["hit"] / acc["n"]) * 100, 1),
            "brier": round(acc["brier"] / acc["n"], 4),
            "n": acc["n"],
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--batters", type=int, default=40)
    a = ap.parse_args()
    if not a.backtest:
        raise SystemExit(
            "This model is backtest-only until its calibration is reviewed.\n"
            "Run: python -m engine.props_model_tb --backtest")
    res = backtest(a.season, sample_batters=a.batters)
    print(json.dumps(res, indent=1))
    out = Path("site/public/data/props_model_tb_backtest.json")
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, indent=1))
    os.replace(tmp, out)


if __name__ == "__main__":
    main()
