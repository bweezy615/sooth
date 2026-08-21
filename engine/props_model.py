"""Pitcher-strikeout projection — our first prop model, built to be graded.

The research that motivated this found two things worth building on:
prop markets are the least efficient lines books offer, and prop lines are
set at the MEDIAN of the outcome distribution. So this model projects the
whole distribution, not a point estimate: strikeouts in a start are treated
as Poisson around an expected rate, and what we publish is P(over the line)
next to the market's de-vigged probability — a like-for-like comparison.

The projection itself is deliberately simple and fully inspectable:

    lambda = expected batters faced x blended K-per-batter x opponent factor

  - expected BF: recency-weighted average of the pitcher's last starts
  - K/BF: last-5 rate shrunk toward season rate (0.6 / 0.4)
  - opponent factor: opposing team's K%% relative to league, capped +-20%%

Everything comes from MLB's free StatsAPI. No proprietary feeds, no scraped
products, and the walk-forward accuracy check grades the model on starts it
had not seen — the same discipline as the NFL backtest, published the same
way whether it flatters us or not.

    python -m engine.props_model              # annotate props.json
    python -m engine.props_model --backtest   # walk-forward accuracy report
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

import requests

from .hitrates import API, find_player, norm

RECENT_W = [0.35, 0.25, 0.18, 0.12, 0.10]   # newest first, sums to 1
SHRINK_RECENT = 0.6                          # weight on last-5 K/BF vs season
OPP_CAP = 0.20                               # opponent factor clamp
LEAGUE_KPCT_FALLBACK = 0.222


def over_threshold(line: float) -> int:
    """Smallest strikeout count that WINS an over at this line.

    A half line cannot push, so 5.5 needs 6. A whole line can: at 6.0 a
    6-strikeout start returns the stake, it does not win, so the over needs 7.
    Using ceil() for both counted that push as a win and inflated p_over on
    every whole-number line.
    """
    return math.ceil(line) if line != int(line) else int(line) + 1


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for Poisson(lam)."""
    if lam <= 0:
        return 0.0
    term = math.exp(-lam)
    cdf = 0.0
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def pitcher_team(pid: int, session: requests.Session) -> str | None:
    r = session.get(f"{API}/people/{pid}",
                    params={"hydrate": "currentTeam"}, timeout=20)
    if r.status_code != 200:
        return None
    people = r.json().get("people", [])
    if not people:
        return None
    return ((people[0].get("currentTeam") or {}).get("name"))


def pitching_log(pid: int, season: int, session: requests.Session) -> list[dict]:
    r = session.get(f"{API}/people/{pid}/stats",
                    params={"stats": "gameLog", "group": "pitching",
                            "season": season}, timeout=20)
    if r.status_code != 200:
        return []
    for s in r.json().get("stats", []):
        out = []
        for sp in s.get("splits", []):
            st = sp.get("stat", {})
            bf = st.get("battersFaced")
            k = st.get("strikeOuts")
            if bf is None or k is None:
                continue
            try:
                out.append({"bf": float(bf), "k": float(k),
                            "opp": (sp.get("opponent") or {}).get("id")})
            except (TypeError, ValueError):
                continue
        return out
    return []


def team_k_rates(season: int, session: requests.Session) -> dict:
    """team name (normalised) and id -> (K%, PA). One call for the league."""
    r = session.get(f"{API}/teams/stats",
                    params={"season": season, "sportIds": 1,
                            "group": "hitting", "stats": "season"},
                    timeout=25)
    rates: dict = {"_league": None}
    if r.status_code != 200:
        return rates
    tot_k = tot_pa = 0.0
    for s in r.json().get("stats", []):
        for sp in s.get("splits", []):
            st = sp.get("stat", {})
            team = sp.get("team", {})
            try:
                k = float(st.get("strikeOuts"))
                pa = float(st.get("plateAppearances"))
            except (TypeError, ValueError):
                continue
            if pa <= 0:
                continue
            rates[norm(team.get("name", ""))] = (k / pa, pa)
            rates[team.get("id")] = (k / pa, pa)
            tot_k += k
            tot_pa += pa
    rates["_league"] = (tot_k / tot_pa) if tot_pa else None
    return rates


def project(log: list[dict], opp_kpct: float | None,
            league_kpct: float) -> dict | None:
    """Expected-strikeout lambda from a pitcher's prior starts."""
    if len(log) < 3:
        return None                      # too thin to project honestly
    recent = log[-5:][::-1]              # newest first
    w = RECENT_W[:len(recent)]
    wsum = sum(w)
    exp_bf = sum(wi * g["bf"] for wi, g in zip(w, recent)) / wsum
    r_bf = sum(g["bf"] for g in recent)
    r_k = sum(g["k"] for g in recent)
    s_bf = sum(g["bf"] for g in log)
    s_k = sum(g["k"] for g in log)
    if r_bf <= 0 or s_bf <= 0:
        return None
    kbf = SHRINK_RECENT * (r_k / r_bf) + (1 - SHRINK_RECENT) * (s_k / s_bf)
    opp = 1.0
    if opp_kpct and league_kpct:
        opp = max(1 - OPP_CAP, min(1 + OPP_CAP, opp_kpct / league_kpct))
    lam = exp_bf * kbf * opp
    return {"lam": lam, "exp_bf": exp_bf, "kbf": kbf, "opp_factor": opp}


def annotate(props_path: str = "site/public/data/props.json",
             season: int = 2026) -> dict:
    path = Path(props_path)
    doc = json.loads(path.read_text())
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-props-model/1.0 (+https://sooth.bet)"

    # Imported here rather than at module scope: props_model_tb imports
    # over_threshold from this module, so a top-level import would be circular.
    from . import props_model_tb as tb

    teams = team_k_rates(season, session)
    league = (teams.get("_league") or LEAGUE_KPCT_FALLBACK)
    bat_league = tb.league_batting_rates(season, session)

    pid_cache: dict = {}
    log_cache: dict = {}
    bat_cache: dict = {}
    looked = modeled = 0
    tb_looked = tb_modeled = 0

    for board in doc.get("boards", []):
        if board["sport"] != "mlb":
            continue
        for ev in board["events"]:
            for p in ev["props"]:
                if p["market"] == "batter_total_bases":
                    # Off unless explicitly asked for. tbconv-v1 is not cleared
                    # to publish: held-out regression slope 0.214, never graded
                    # on a board population, and the strikeout model it shares a
                    # contract with measured no edge at all. props.json is a
                    # public file, so writing model blocks into it IS
                    # publishing, and doing that silently would contradict the
                    # record in docs/reports/props-model-negative-result.md.
                    if not os.environ.get("PROPS_MODEL_TB"):
                        continue
                    tb_looked += 1
                    if _annotate_tb(p, tb, bat_league, bat_cache, pid_cache,
                                    session, season):
                        tb_modeled += 1
                    continue
                if p["market"] != "pitcher_strikeouts":
                    continue
                looked += 1
                name = p["player"]
                if name not in pid_cache:
                    pid_cache[name] = find_player(name, session)
                    time.sleep(0.15)
                pid = pid_cache[name]
                if not pid:
                    continue
                if pid not in log_cache:
                    log_cache[pid] = pitching_log(pid, season, session)
                    time.sleep(0.15)
                log = log_cache[pid]
                # Opponent = whichever matchup team the pitcher is NOT on.
                own = pitcher_team(pid, session)
                time.sleep(0.1)
                opp_name = None
                if own:
                    if norm(own) == norm(ev["home"]):
                        opp_name = ev["away"]
                    elif norm(own) == norm(ev["away"]):
                        opp_name = ev["home"]
                opp_rate = None
                if opp_name:
                    rate = teams.get(norm(opp_name))
                    if rate:
                        opp_rate = rate[0]
                proj = project(log, opp_rate, league)
                if not proj:
                    continue
                line = float(p["line"])
                need = over_threshold(line)
                p_over = poisson_sf(need, proj["lam"])

                # Prefer the precise de-vigged probability when the board
                # carries it. fair_price is an already-rounded integer American
                # price, so recomputing from it feeds avoidable rounding noise
                # straight into delta_pts — the number the page shows as our
                # model against the market. engine.props publishes only
                # fair_price today, so keep the round-trip as the fallback.
                fair_over = p["over"].get("fair_prob")
                if fair_over is None:
                    fp = p["over"]["fair_price"]
                    fair_over = ((-fp) / ((-fp) + 100.0)) if fp < 0 else (100.0 / (fp + 100.0))
                p["model"] = {
                    "proj_k": round(proj["lam"], 2),
                    "p_over": round(p_over, 4),
                    "market_over": round(fair_over, 4),
                    "delta_pts": round((p_over - fair_over) * 100, 1),
                    "n_starts": len(log),
                    "version": "kpoisson-v1",
                }
                modeled += 1

    doc["props_model"] = {"version": "kpoisson-v1", "season": season,
                          "modeled": modeled, "eligible": looked,
                          "method": "poisson over expected BF x blended K/BF "
                                    "x opponent K% factor; free MLB StatsAPI"}
    # Separate key rather than folding into props_model above: that block is
    # the strikeout model's scorecard and its version string is graded against
    # the strikeout ledger. Two models, two scorecards.
    doc["props_model_tb"] = {"version": tb.VERSION, "season": season,
                             "modeled": tb_modeled, "eligible": tb_looked,
                             "method": "exact convolution of per-PA base "
                                       "outcomes over the plate-appearance "
                                       "distribution; free MLB StatsAPI",
                             "aggregate_bias_pts": -1.2,
                             "bucket_miscalibration_pts": 13.1,
                             "bias_note": "aggregate calibration is good "
                                          "(-1.2pts) but that is cancellation. "
                                          "Bucketed by predicted probability "
                                          "both this and kpoisson-v1 are wrong "
                                          "by 7-17pts. Cause is mean scaling, "
                                          "not variance: held-out regression "
                                          "slope 0.63 for K and 0.21 for TB, "
                                          "so projections over-spread. Slope "
                                          "correction fixes the centre but is "
                                          "unvalidated at tail lines. Neither "
                                          "market is cleared to post."}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, path)
    return doc["props_model"]


def _annotate_tb(p: dict, tb, bat_league: dict, bat_cache: dict,
                 pid_cache: dict, session: requests.Session,
                 season: int) -> bool:
    """Attach a total-bases model block. Returns True if one was written.

    Emits n_games rather than n_starts on purpose: total bases accumulate per
    appearance, not per start, so n_starts would misdescribe what was counted.
    """
    name = p["player"]
    if name not in pid_cache:
        pid_cache[name] = find_player(name, session)
        time.sleep(0.15)
    pid = pid_cache[name]
    if not pid:
        return False
    if pid not in bat_cache:
        bat_cache[pid] = tb.batting_log(pid, season, session)
        time.sleep(0.15)
    log = bat_cache[pid]
    proj = tb.project(log, bat_league)
    if not proj:
        return False
    need = over_threshold(float(p["line"]))
    p_over = tb.sf(proj["pmf"], need)
    fair_over = p["over"].get("fair_prob")
    if fair_over is None:
        fp = p["over"]["fair_price"]
        fair_over = ((-fp) / ((-fp) + 100.0)) if fp < 0 else (100.0 / (fp + 100.0))
    p["model"] = {
        "proj_tb": round(proj["exp_tb"], 2),
        "p_over": round(p_over, 4),
        "market_over": round(fair_over, 4),
        "delta_pts": round((p_over - fair_over) * 100, 1),
        "n_games": len(log),
        "version": tb.VERSION,
    }
    return True


def backtest(season: int = 2026, min_starts: int = 4,
             sample_pitchers: int = 40) -> dict:
    """Walk-forward accuracy on real starts the model never saw.

    For every start i >= min_starts of each sampled pitcher, project from
    starts < i (opponent factor off — historical opponent strength as-of
    that date is not cheaply available) and score against the actual Ks.
    Baseline: last-5 mean. Published either way.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "sooth-props-model/1.0 (+https://sooth.bet)"
    r = session.get(f"{API}/stats/leaders",
                    params={"leaderCategories": "strikeouts",
                            "statGroup": "pitching", "season": season,
                            "limit": sample_pitchers, "sportId": 1},
                    timeout=25)
    pids = []
    for cat in r.json().get("leagueLeaders", []):
        for l in cat.get("leaders", []):
            pid = (l.get("person") or {}).get("id")
            if pid:
                pids.append(pid)
    pids = list(dict.fromkeys(pids))[:sample_pitchers]

    n = 0
    abs_err = base_err = 0.0
    within1 = 0
    cover_lo = 0        # calibration: how often actual falls in 80% interval
    for pid in pids:
        log = pitching_log(pid, season, session)
        time.sleep(0.12)
        for i in range(min_starts, len(log)):
            prior, actual = log[:i], log[i]["k"]
            proj = project(prior, None, LEAGUE_KPCT_FALLBACK)
            if not proj:
                continue
            lam = proj["lam"]
            n += 1
            abs_err += abs(lam - actual)
            recent = prior[-5:]
            base = sum(g["k"] for g in recent) / len(recent)
            base_err += abs(base - actual)
            if abs(lam - actual) <= 1:
                within1 += 1
            # 80% central Poisson interval by simple quantile walk
            lo = hi = None
            c = 0.0
            term = math.exp(-lam)
            for k in range(0, 40):
                c += term
                if lo is None and c >= 0.10:
                    lo = k
                if hi is None and c >= 0.90:
                    hi = k
                    break
                term *= lam / (k + 1)
            if lo is not None and hi is not None and lo <= actual <= hi:
                cover_lo += 1
    return {"season": season, "pitchers": len(pids), "starts_graded": n,
            "mae": round(abs_err / n, 3) if n else None,
            "baseline_last5_mae": round(base_err / n, 3) if n else None,
            "within_1k_pct": round(within1 / n * 100, 1) if n else None,
            "poisson80_coverage_pct": round(cover_lo / n * 100, 1) if n else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default="site/public/data/props.json")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--backtest", action="store_true")
    a = ap.parse_args()
    if a.backtest:
        res = backtest(a.season)
        print(json.dumps(res, indent=1))
        out = Path("site/public/data/props_model_backtest.json")
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(res, indent=1))
        os.replace(tmp, out)
    else:
        res = annotate(a.props, a.season)
        print(f"modeled {res['modeled']}/{res['eligible']} strikeout props "
              f"({res['version']})")


if __name__ == "__main__":
    main()
