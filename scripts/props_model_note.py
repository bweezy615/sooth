"""Regenerate every figure on /props-model from the evidence on disk.

Why this exists
---------------
`site/public/props-model.html` is the research note that publishes our prop
model failing. It is the page that argues hardest that we are honest about a
negative result, and until 2026-08-28 every one of its ~44 figures was typed
in by hand from a one-off analysis that no longer existed as code. A page
whose whole claim is "you can check this" cannot be the page nobody can check.

This script rebuilds the analysis from two committed inputs and nothing else:

  data/capture/mlb-props/*.jsonl   append-only prop capture (our own)
  data/mlb/pitching_logs_2026.json cached MLB StatsAPI game logs

so anyone who clones the repo reproduces the numbers offline. `--fetch`
refreshes the cache from statsapi.mlb.com; without it the script is offline
and deterministic, which is also how `tests/test_props_model_note.py` runs it.

    python scripts/props_model_note.py --fetch   # refresh the log cache first
    python scripts/props_model_note.py           # recompute + write payload
    python scripts/props_model_note.py --render  # + rewrite the page's figures

Output
------
  site/public/data/props_model_note.json
      { "figures": { "<key>": "<display string>" }, "detail": {...} }

  site/public/props-model.html
      every figure lives in an element carrying data-f="<key>"; --render
      writes the display string into it. No digit on that page is authored in
      the markup, and the test fails if the two disagree.

What moved when this was first regenerated (2026-08-28)
-------------------------------------------------------
The board-population result reproduced in shape and moved in detail: the
sample is larger (the old run could not resolve a dozen pitchers by name, and
five more days of capture have landed), and the model's win rate on its own
disagreements came back lower than the 48.1% published.

One figure did not reproduce at all, and that is the finding. The page said
the model carries information on all pitcher-starts (Platt slope 0.48) and
none on the games books post a prop on (-0.07), and attributed the whole drop
to books choosing which games to hang. Regenerating it shows the 0.48 was
measured against a single league-median line applied to every pitcher. Give
the line the one thing every real posted line already knows -- which pitcher
is on the mound -- and the slope falls to ~0.20 on the same starts, a drop of
more than four standard errors. The further fall to -0.11 on real board props
is under one standard error and is not established at this sample size. The
model still has no measurable edge on real props; the published explanation
for why was wrong.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.props_board import implied_prob, median  # noqa: E402
from engine.props_model import (LEAGUE_KPCT_FALLBACK, over_threshold,  # noqa: E402
                                poisson_sf, project)
from engine.schema import canonical_book  # noqa: E402

CAPTURE = ROOT / "data/capture/mlb-props"
LOG_CACHE = ROOT / "data/mlb/pitching_logs_2026.json"
FIGURES = ROOT / "site/content/_figures.json"
OUT = ROOT / "site/public/data/props_model_note.json"
PAGE = ROOT / "site/public/props-model.html"

SEASON = 2026
MIN_BOOKS = 3          # a prop counts only where 3+ books priced BOTH sides
MARKET = "pitcher_strikeouts"

# The experiment is closed as of this game date, and the capture cron keeps
# appending past it. Without the pin, every routine "capture: mlb props
# snapshot" commit would silently change a published figure and redden the
# gate on work nobody did. Moving it is a deliberate act: pass --through, read
# the diff, and if the numbers move, the page says they moved. A test fails
# once the capture has run a month past this date, so a pinned window cannot
# quietly become a stale one.
#
# Extended 2026-09-03 from 2026-08-26. Routine refresh, not a correction:
# 32 of 45 figures moved, all small, and the page's conclusion is unchanged
# (won 44.7% of 237 disagreements, board slope CI still straddles zero), so
# nothing was withdrawn and the correction record below is untouched.
# The pin is the newest CLOSED game date, not the newest capture file. A game
# date runs to observed_at + MLB_DAY_OFFSET, so at the time of the move the
# 2026-09-02 file was still accumulating rows; pinning into it would have let
# a routine capture commit move a published figure, which is the one thing
# this pin exists to prevent.
WINDOW_THROUGH = "2026-09-01"
STALE_AFTER_DAYS = 30

# A game's official MLB date is its local date. Every start in the majors falls
# on the UTC-8h date: the earliest first pitch (~11:35 ET = 15:35Z) lands the
# same day, the latest (~22:10 PT = 05:10Z next day) lands the previous one.
MLB_DAY_OFFSET = timedelta(hours=8)


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def platt(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Fit y ~ sigmoid(a + b*x) by IRLS. Returns (b, se(b)).

    b is the weight the model's own log-odds deserve: 1.0 means take them at
    face value, 0.0 means they carry no information about the outcome. The
    standard error comes from the inverse Fisher information, so the interval
    quoted on the page is the model's own, not an eyeballed one.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(2)
    for _ in range(300):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        w = np.clip(p * (1 - p), 1e-9, None)
        step = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - p))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-11:
            break
    p = 1.0 / (1.0 + np.exp(-(X @ beta)))
    w = np.clip(p * (1 - p), 1e-9, None)
    cov = np.linalg.inv(X.T @ (X * w[:, None]))
    return float(beta[1]), float(math.sqrt(cov[1, 1]))


def platt_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Same fit, returning (intercept, slope) for use as a recalibration map."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(2)
    for _ in range(300):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        w = np.clip(p * (1 - p), 1e-9, None)
        step = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - p))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-11:
            break
    return float(beta[0]), float(beta[1])


def ece(p: np.ndarray, y: np.ndarray, bins: int = 5) -> float:
    """Expected calibration error over equal-COUNT bins, in points.

    Two deliberate departures from engine/calibrate.py, both forced by this
    data and both recorded on the page:

    Equal-count rather than fixed-width bins. Every probability here, ours and
    the market's, sits within a few points of the base rate. Fixed 0.1-wide
    bins put the whole market in one bucket, at which point its "calibration
    error" is just its aggregate bias and the statistic cannot see a
    calibration problem at all.

    Five bins rather than ten. At a few hundred props ten buckets is a couple
    of dozen coin flips a bucket. The page used to quote the single worst
    bucket of ten, which on this sample is a two-observation artifact that
    swings tens of points run to run; that is why it is no longer quoted.
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(p, kind="stable")
    tot = 0.0
    for chunk in np.array_split(order, bins):
        if len(chunk) == 0:
            continue
        tot += len(chunk) / len(p) * abs(p[chunk].mean() - y[chunk].mean())
    return tot * 100.0


def brier(p: np.ndarray, y: np.ndarray) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(((p - y) ** 2).mean())


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------

def mlb_date(commence_time: str) -> str:
    d = datetime.fromisoformat(str(commence_time).replace("Z", "+00:00"))
    return (d - MLB_DAY_OFFSET).date().isoformat()


def load_capture() -> list[dict]:
    """Every priced strikeout quote we ever captured, book identity normalised.

    Reads only the top-level {selection, price} shape props_capture writes.
    The directory also holds older nested rows from engine.props (both sides
    under "over"/"under", start time under "kickoff"); those are real evidence
    and stay on disk, but they were never this module's shape.
    """
    rows: list[dict] = []
    for f in sorted(CAPTURE.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("market") != MARKET:
                continue
            if r.get("selection") is None or r.get("price") is None:
                continue
            r["book"] = canonical_book(r.get("book", ""))
            rows.append(r)
    return rows


def capture_counts() -> dict:
    """Raw quote counts per market, for the page's "we had N quotes" sentence."""
    n: collections.Counter = collections.Counter()
    for f in sorted(CAPTURE.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                n[json.loads(line).get("market")] += 1
    return dict(n)


def board_props(rows: list[dict]) -> list[dict]:
    """Props that reached a real board: 3+ books pricing BOTH sides.

    Newest quote per (prop, side, book), the same rule props_board.py uses to
    build the live grid, so this population is the one the model would have
    deployed on rather than every line anyone ever posted.
    """
    latest: dict[tuple, dict] = {}
    for r in rows:
        key = (r["event_id"], r["player"], r["line"], r["selection"], r["book"])
        prev = latest.get(key)
        if prev is None or r["observed_at"] > prev["observed_at"]:
            latest[key] = r

    grouped: dict[tuple, dict] = collections.defaultdict(
        lambda: {"books": collections.defaultdict(dict), "rep": None})
    for (event_id, player, line, selection, book), r in latest.items():
        g = grouped[(event_id, player, line)]
        g["books"][book][selection] = r
        if g["rep"] is None:
            g["rep"] = r

    out = []
    for (event_id, player, line), g in grouped.items():
        two = [b for b, s in g["books"].items() if "over" in s and "under" in s]
        if len(two) < MIN_BOOKS:
            continue
        over = median([implied_prob(g["books"][b]["over"]["price"]) for b in two])
        under = median([implied_prob(g["books"][b]["under"]["price"]) for b in two])
        out.append({
            "player": player,
            "date": mlb_date(g["rep"]["commence_time"]),
            "line": float(line),
            "n_books": len(two),
            # de-vigged: the two sides' median implied probs normalised to sum
            # to 1. This is the market's own opinion with its margin removed,
            # which is the only thing our probability can fairly be compared to.
            "market_over": over / (over + under),
        })
    out.sort(key=lambda p: (p["date"], p["player"], p["line"]))
    return out


def fetch_logs(names: list[str]) -> dict:
    """Refresh the cached MLB game logs. Only path that touches the network."""
    import requests

    from engine.hitrates import API, norm

    s = requests.Session()
    s.headers["User-Agent"] = "sooth-props-model/1.0 (+https://sooth.bet)"

    def resolve(name: str) -> int | None:
        """Name -> MLB id.

        hitrates.find_player refuses every duplicate name outright, which is
        right for a page that would otherwise publish the wrong man's record
        but drops working starters (Hunter Brown, Luis Castillo) from this
        analysis entirely -- part of why the original run graded 194 props and
        this one grades more. A strikeout prop names a pitcher, so an active
        pitcher is the only candidate that can be meant. Punctuation is
        stripped before comparing, but that only rescues a spelling the API
        search still finds; "JT Ginn" returns nothing at all for "J.T. Ginn"
        and stays unresolved, which the payload records rather than guesses.
        Still refuses when two active pitchers share a name.
        """
        r = s.get(f"{API}/people/search", params={"names": name}, timeout=20)
        if r.status_code != 200:
            return None
        people = r.json().get("people", [])
        flat = re.sub(r"[^a-z0-9]", "", norm(name))
        exact = [p for p in people
                 if re.sub(r"[^a-z0-9]", "", norm(p.get("fullName", ""))) == flat]
        if len(exact) == 1:
            return exact[0].get("id")
        live = [p for p in exact if p.get("active")
                and (p.get("primaryPosition") or {}).get("abbreviation") == "P"]
        return live[0].get("id") if len(live) == 1 else None

    out: dict = {}
    for name in names:
        pid = resolve(name)
        time.sleep(0.12)
        if not pid:
            out[name] = {"pid": None, "log": []}
            continue
        r = s.get(f"{API}/people/{pid}/stats",
                  params={"stats": "gameLog", "group": "pitching",
                          "season": SEASON}, timeout=25)
        time.sleep(0.12)
        log = []
        for block in r.json().get("stats", []):
            for sp in block.get("splits", []):
                st = sp.get("stat", {})
                if st.get("battersFaced") is None or st.get("strikeOuts") is None:
                    continue
                log.append({"d": sp.get("date"),
                            "bf": float(st["battersFaced"]),
                            "k": float(st["strikeOuts"]),
                            "gs": int(st.get("gamesStarted") or 0)})
            break
        out[name] = {"pid": pid, "log": log}
    LOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LOG_CACHE.write_text(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return out


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------

def grade(logs: dict, player: str, date: str, line: float) -> dict | None:
    """Walk-forward projection and outcome for one pitcher-game at one line.

    The projection sees only appearances strictly before this game's date, so
    no figure on the page uses information the model would not have had. The
    opponent factor is off for the same reason -- opposing-team K% as-of a
    past date is not available from the free API, and using today's would be
    reaching forward. engine.props_model.backtest() already omits it and says so.
    """
    entry = logs.get(player) or {}
    if not entry.get("pid"):
        return None
    log = entry["log"]
    i = next((j for j, g in enumerate(log) if g["d"] == date), None)
    if i is None:
        # Books occasionally carry a start time that lands us a day either
        # side of the official date (doubleheaders, suspended games).
        i = next((j for j, g in enumerate(log)
                  if abs((datetime.fromisoformat(g["d"])
                          - datetime.fromisoformat(date)).days) <= 1), None)
    if i is None:
        return None                       # scratched, or the game never happened
    g = log[i]
    if g["gs"] != 1:
        return None                       # relief appearance: not a start prop
    proj = project(log[:i], None, LEAGUE_KPCT_FALLBACK)
    if not proj:
        return None                       # under three prior appearances
    need = over_threshold(line)
    if line == int(line) and g["k"] == line:
        return None                       # a whole line can push; a push is not a result
    return {"p_over": poisson_sf(need, proj["lam"]),
            "over": 1 if g["k"] >= need else 0,
            "k": g["k"], "lam": proj["lam"]}


def general_population(logs: dict, typical: dict[str, float],
                       line_for) -> tuple[np.ndarray, np.ndarray]:
    """Every walk-forward start by the pitchers who reached a board, graded at
    whatever line `line_for(player)` says. The line rule is the whole point of
    this function -- see the note in main()."""
    p, y = [], []
    for player, entry in sorted(logs.items()):
        if not entry.get("pid") or player not in typical:
            continue
        for g in entry["log"]:
            if g["gs"] != 1:
                continue
            r = grade(logs, player, g["d"], line_for(player))
            if r:
                p.append(r["p_over"])
                y.append(r["over"])
    return np.array(p), np.array(y)


# --------------------------------------------------------------------------
# the payload
# --------------------------------------------------------------------------

def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def pts(x: float) -> str:
    return f"{x:.1f} pts"


def build(through: str = WINDOW_THROUGH) -> dict:
    rows = load_capture()
    if not rows:
        raise SystemExit("no strikeout capture on disk")
    if not LOG_CACHE.exists():
        raise SystemExit(f"{LOG_CACHE} missing — run with --fetch first")
    logs = json.loads(LOG_CACHE.read_text())

    props = [p for p in board_props(rows) if p["date"] <= through]
    typical = {p: float(np.median(v)) for p, v in
               _lines_by_pitcher(rows).items()}

    # ---- the board population: the props the model would have deployed on --
    graded, skipped = [], collections.Counter()
    for p in props:
        r = grade(logs, p["player"], p["date"], p["line"])
        if not r:
            skipped["ungradeable"] += 1
            continue
        graded.append({**p, **r})
    if not graded:
        raise SystemExit("no gradeable board props")

    n = len(graded)
    P = np.array([g["p_over"] for g in graded])
    M = np.array([g["market_over"] for g in graded])
    Y = np.array([g["over"] for g in graded])
    delta = np.abs(P - M) * 100
    dis = delta >= 3
    n_dis = int(dis.sum())
    won = int(((P[dis] > M[dis]) == (Y[dis] == 1)).sum())
    won_pct = won / n_dis
    se_pts = math.sqrt(0.25 / n_dis) * 100

    b_board, se_board = platt(logit(P), Y)

    # ---- the same model, three ways of choosing the line -------------------
    #
    # This is the decomposition that replaced the page's original claim. The
    # question is where the model's apparent information goes, and the answer
    # turns on what the line knows:
    #
    #   one league-median line for every pitcher  -- the line knows nothing
    #   the pitcher's own typical board line      -- the line knows who is pitching
    #   the line books actually posted            -- the real thing
    #
    # The first is what the published 0.48 was measured against. Any real
    # posted line is at least as informed as the second.
    league_line = float(np.median([float(r["line"]) for r in rows]))
    gp_flat, gy_flat = general_population(logs, typical, lambda _p: league_line)
    gp_typ, gy_typ = general_population(logs, typical, lambda p: typical[p])
    b_flat, se_flat = platt(logit(gp_flat), gy_flat)
    b_typ, se_typ = platt(logit(gp_typ), gy_typ)

    # the control that isolates game selection from line specification:
    # the SAME board games, graded at the pitcher's typical line instead of
    # the posted one.
    ctrl = [grade(logs, p["player"], p["date"], typical[p["player"]])
            for p in props if p["player"] in typical]
    ctrl = [c for c in ctrl if c]
    b_ctrl, se_ctrl = platt(logit(np.array([c["p_over"] for c in ctrl])),
                            np.array([c["over"] for c in ctrl]))

    def zdiff(a, sa, b, sb):
        return (a - b) / math.sqrt(sa ** 2 + sb ** 2)

    z_line = zdiff(b_flat, se_flat, b_typ, se_typ)
    z_select = zdiff(b_typ, se_typ, b_ctrl, se_ctrl)
    z_posted = zdiff(b_ctrl, se_ctrl, b_board, se_board)

    # ---- can it be salvaged as an honest probability? ----------------------
    # Fit a Platt recalibration and score it out of sample. Five-fold rather
    # than one 50/50 split: props are date-ordered and the over rate wanders
    # day to day, so a single split put a 49.7% half against a 37.8% half and
    # what it then measured was mostly that mismatch. Out-of-fold gives every
    # prop a probability from a map fitted without it and uses all 286.
    folds = 5
    idx = np.arange(n)
    recal = np.zeros(n)
    fit_slopes = []
    for f in range(folds):
        te_f = idx[f::folds]
        tr_f = np.setdiff1d(idx, te_f)
        a_fit, b_fit = platt_fit(logit(P[tr_f]), Y[tr_f])
        fit_slopes.append(b_fit)
        recal[te_f] = 1.0 / (1.0 + np.exp(-(a_fit + b_fit * logit(P[te_f]))))
    te = idx

    starts = sorted(sum(1 for g in e["log"] if g["gs"] == 1)
                    for p, e in logs.items() if e.get("pid") and p in typical)
    quotes = capture_counts()
    nfl = json.loads(FIGURES.read_text())
    ind = nfl["evaluation_a"]["results"]["independent"]
    w, l, _pushes = (int(x) for x in ind["ats_record"].split("-"))

    detail = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": {
            "board_filter": f"{MIN_BOOKS}+ books pricing both sides",
            "walk_forward": "projection uses only appearances before the game",
            "opponent_factor": "off - as-of opposing-team K% is not available",
            "window_through": through,
            "calibration_statistic": "expected calibration error (ECE)",
            "league_line": league_line,
        },
        "window": {"first": graded[0]["date"], "last": graded[-1]["date"]},
        "board": {
            "n": n, "ungradeable": int(skipped["ungradeable"]),
            "n_props_seen": len(props),
            "model_over": float(P.mean()), "market_over": float(M.mean()),
            "actual_over": float(Y.mean()),
            "mean_abs_delta_pts": float(delta.mean()),
            "n_disagree": n_dis, "won": won, "won_pct": won_pct,
            "se_pts": se_pts,
            "slope": b_board, "slope_se": se_board,
            "brier_model": brier(P, Y), "brier_market": brier(M, Y),
            "ece_model": ece(P, Y), "ece_market": ece(M, Y),
            "market_bias_pts": float((M.mean() - Y.mean()) * 100),
            "market_bias_sigma": float((M.mean() - Y.mean())
                                       / math.sqrt(Y.mean() * (1 - Y.mean()) / n)),
        },
        "slopes": {
            "flat_line": {"n": int(len(gp_flat)), "slope": b_flat, "se": se_flat,
                          "ece": ece(gp_flat, gy_flat)},
            "typical_line": {"n": int(len(gp_typ)), "slope": b_typ, "se": se_typ,
                             "ece": ece(gp_typ, gy_typ)},
            "board_typical_line": {"n": len(ctrl), "slope": b_ctrl, "se": se_ctrl},
            "board_posted_line": {"n": n, "slope": b_board, "se": se_board},
            "z_line_specification": z_line,
            "z_game_selection": z_select,
            "z_posted_line": z_posted,
        },
        "salvage": {
            "folds": folds, "n_test": int(len(te)),
            "fit_slope_min": float(min(fit_slopes)),
            "fit_slope_max": float(max(fit_slopes)),
            "raw": {"ece": ece(P, Y), "brier": brier(P, Y)},
            "recalibrated": {"ece": ece(recal, Y), "brier": brier(recal, Y),
                             "min": float(recal.min()), "max": float(recal.max()),
                             "mean": float(recal.mean())},
            "market": {"ece": ece(M, Y), "brier": brier(M, Y)},
        },
        "coverage": {
            "pitchers": len(starts),
            "starts_p10": starts[int(0.1 * len(starts))],
            "starts_p90": starts[int(0.9 * len(starts))],
            "quotes_strikeouts": quotes.get(MARKET, 0),
            "quotes_total_bases": quotes.get("batter_total_bases", 0),
        },
        "nfl": {"ats_pct": ind["ats_pct"], "decided": w + l,
                "breakeven": nfl["breakeven_ats"]},
    }

    d = detail
    figures = {
        "window.first": _pretty(d["window"]["first"]),
        "window.last": _pretty(d["window"]["last"]),
        "board.n": f"{n:,}",
        "board.model_over": pct(d["board"]["model_over"]),
        "board.market_over": pct(d["board"]["market_over"]),
        "board.actual_over": pct(d["board"]["actual_over"]),
        "board.mean_delta": pts(d["board"]["mean_abs_delta_pts"]),
        "board.mean_delta_bare": f"{d['board']['mean_abs_delta_pts']:.1f}",
        "board.n_disagree": f"{n_dis:,}",
        "board.disagree_of": f"{n_dis:,} of {n:,}",
        "board.disagree_share": f"{n_dis / n * 100:.0f}%",
        "board.won_pct": pct(won_pct),
        "board.se": f"{se_pts:.1f}",
        "board.market_bias": pts(d["board"]["market_bias_pts"]),
        "board.market_sigma": f"{d['board']['market_bias_sigma']:.1f}",
        "slope.flat_n": f"{d['slopes']['flat_line']['n']:,}",
        "slope.flat": f"{b_flat:+.2f}",
        "slope.typical_n": f"{d['slopes']['typical_line']['n']:,}",
        "slope.typical": f"{b_typ:+.2f}",
        "slope.board_n": f"{n:,}",
        "slope.board": f"{b_board:+.2f}",
        "slope.board_ci": f"{b_board - 1.96 * se_board:+.2f} to "
                          f"{b_board + 1.96 * se_board:+.2f}",
        "slope.board_typical": f"{b_ctrl:+.2f}",
        "slope.board_typical_n": f"{len(ctrl):,}",
        "slope.z_line": f"{abs(z_line):.1f}",
        "slope.z_select": f"{abs(z_select):.1f}",
        "slope.z_posted": f"{abs(z_posted):.1f}",
        "salvage.folds": str(d["salvage"]["folds"]),
        "salvage.raw_ece": pts(d["salvage"]["raw"]["ece"]),
        "salvage.raw_brier": f"{d['salvage']['raw']['brier']:.4f}",
        "salvage.recal_ece": pts(d["salvage"]["recalibrated"]["ece"]),
        "salvage.recal_brier": f"{d['salvage']['recalibrated']['brier']:.4f}",
        "salvage.market_ece": pts(d["salvage"]["market"]["ece"]),
        "salvage.market_brier": f"{d['salvage']['market']['brier']:.4f}",
        "salvage.band": f"{d['salvage']['recalibrated']['min'] * 100:.0f}% and "
                        f"{d['salvage']['recalibrated']['max'] * 100:.0f}%",
        "salvage.mean": pct(d["salvage"]["recalibrated"]["mean"]),
        "salvage.fit_slopes": f"{d['salvage']['fit_slope_min']:+.2f} and "
                              f"{d['salvage']['fit_slope_max']:+.2f}",
        "cover.pitchers": f"{d['coverage']['pitchers']:,}",
        "cover.starts": f"{d['coverage']['starts_p10']}–"
                        f"{d['coverage']['starts_p90']}",
        "cover.k_quotes": f"{d['coverage']['quotes_strikeouts']:,}",
        "cover.tb_quotes": f"{d['coverage']['quotes_total_bases']:,}",
        "cover.league_line": f"{league_line:g}",
        "nfl.ats": pct(d["nfl"]["ats_pct"]),
        "nfl.decided": f"{d['nfl']['decided']:,}",
        "nfl.breakeven": pct(d["nfl"]["breakeven"]),
    }
    return {"figures": figures, "detail": detail}


def _lines_by_pitcher(rows: list[dict]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = collections.defaultdict(list)
    for r in rows:
        out[r["player"]].append(float(r["line"]))
    return out


def _pretty(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

TAG = re.compile(r'(<(\w+)\b[^>]*\bdata-f="([^"]+)"[^>]*>)(.*?)(</\2>)', re.S)


def render(html: str, figures: dict[str, str]) -> tuple[str, list[str]]:
    """Replace the body of every data-f element with its figure.

    Deliberately dumb: one regex, no HTML parser, no digits invented. An
    unknown key is returned rather than guessed at, so --render refuses to
    half-write the page.
    """
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(3)
        if key not in figures:
            missing.append(key)
            return m.group(0)
        return m.group(1) + figures[key] + m.group(5)

    return TAG.sub(sub, html), missing


def page_figures(html: str) -> dict[str, str]:
    """What the page currently displays, keyed the same way. Used by the test."""
    return {m.group(3): m.group(4) for m in TAG.finditer(html)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true",
                    help="refresh data/mlb/pitching_logs_2026.json from StatsAPI")
    ap.add_argument("--render", action="store_true",
                    help="also rewrite the figures in site/public/props-model.html")
    ap.add_argument("--through", default=WINDOW_THROUGH,
                    help="last game date in the population (see WINDOW_THROUGH)")
    a = ap.parse_args()

    if a.fetch:
        names = sorted({r["player"] for r in load_capture()})
        print(f"fetching {len(names)} pitcher logs...")
        logs = fetch_logs(names)
        print(f"resolved {sum(1 for v in logs.values() if v['pid'])}/{len(names)}")

    doc = build(a.through)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, OUT)
    d = doc["detail"]
    print(f"board population n={d['board']['n']} "
          f"({d['window']['first']}..{d['window']['last']}), "
          f"won {d['board']['won_pct'] * 100:.1f}% of "
          f"{d['board']['n_disagree']} disagreements")
    print(f"slope  flat {d['slopes']['flat_line']['slope']:+.3f}  "
          f"typical {d['slopes']['typical_line']['slope']:+.3f}  "
          f"board {d['slopes']['board_posted_line']['slope']:+.3f}")

    if a.render:
        html = PAGE.read_text(encoding="utf-8")
        new, missing = render(html, doc["figures"])
        if missing:
            raise SystemExit(f"page asks for figures that do not exist: {missing}")
        if new != html:
            PAGE.write_text(new, encoding="utf-8", newline="")
            print(f"rendered {len(page_figures(new))} figures into {PAGE.name}")
        else:
            print("page already current")


if __name__ == "__main__":
    main()
