"""Refit EloConfig on college football, walk-forward, and report it.

``docs/plans/college-football.md`` Phase 3:

    Every constant in ``EloConfig`` was chosen for a 32-team league with a
    draft and a salary cap. CFB has ~130 FBS teams, no parity mechanism,
    enormous talent spread, and games against unrated FCS opponents. ``k``,
    ``home_advantage``, ``season_carryover`` and ``elo_per_point`` must be
    refit on CFB data, walk-forward, and the refit reported. Reusing NFL
    numbers and publishing the output would be a fabricated model.

This script is that refit.

HOW THE SPLIT AVOIDS FITTING THE ANSWER
---------------------------------------
Elo is already walk-forward within a run — it predicts a game before folding
in its result — but choosing hyperparameters BY the score of a walk-forward run
is not. Pick ``k`` because it scored best over 2002-2025 and the reported
2002-2025 score is no longer out of sample.

So the seasons are split once and the split is never crossed:

  2002-2015  development. The grid search runs here and only here.
  2016-2025  evaluation. Touched once, with the config frozen, to produce the
             numbers below. 2016 is also where ``models/ensemble.py`` starts
             its NFL test, so the two sports' headline spans line up.

WHAT IS AND IS NOT REPORTED
---------------------------
Brier, log loss, accuracy and calibration error against results. **No market
comparison, because there is none to make**: cfbfastR carries no betting
lines, so there is no de-vigged close to score against and no ATS record.
Every number here says "better than nothing", never "better than the market".
See ``engine/adapters/ncaaf.py``.

FBS-vs-FBS is the headline. Games against pooled FCS opposition are ~11% of
the rows and are close to free to predict, so including them flatters every
model equally and measures scheduling rather than skill. Both are printed.

    .venv/bin/python scripts/refit_elo_ncaaf.py
"""

from __future__ import annotations

import itertools
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.adapters.ncaaf import NCAAFAdapter  # noqa: E402
from engine.calibrate import expected_calibration_error  # noqa: E402
from engine.models.elo import EloConfig, EloModel  # noqa: E402

DEV_SEASONS = (2002, 2015)
EVAL_SEASONS = (2016, 2025)

# The grid. Ranges bracket the NFL defaults rather than centring on them,
# because the prior is that a 130-team league with no parity mechanism wants a
# different k and a lower carryover than a 32-team one with a draft.
GRID = {
    "k": [12.0, 20.0, 28.0, 36.0, 44.0],
    "home_advantage": [48.0, 60.0, 72.0, 84.0],
    "season_carryover": [0.50, 0.60, 0.70, 0.80, 0.90],
}


def run_elo(df: pd.DataFrame, config: EloConfig) -> pd.DataFrame:
    """One walk-forward pass: predict each game, then fold in its result.

    Iterates in kickoff order for the same reason the adapter's rest pass does
    — college week numbers are not chronological, and updating ratings in week
    order would let a game inform a prediction made before it was played.
    """
    order = df["start_date"].argsort(kind="stable")
    model = EloModel(config=config)
    probs = np.full(len(df), np.nan)
    diffs = np.full(len(df), np.nan)
    for pos in order:
        r = df.iloc[pos]
        home, away = r["home_key"], r["away_key"]
        season = int(r["season"])
        neutral = bool(r["neutral_site"])
        rest = pd.to_numeric(r["home_rest"], errors="coerce") - pd.to_numeric(
            r["away_rest"], errors="coerce")
        rest = 0.0 if pd.isna(rest) else float(rest)
        p = model.expected(home, away, neutral=neutral, rest_diff=rest,
                           season=season)
        probs[pos] = p
        diffs[pos] = model.rating(home) - model.rating(away) + (
            0.0 if neutral else config.home_advantage)
        if pd.notna(r["home_points"]) and pd.notna(r["away_points"]):
            model.update(home, away,
                         float(r["home_points"]) - float(r["away_points"]),
                         neutral=neutral, rest_diff=rest, season=season)
    out = df.copy()
    out["elo_p"] = probs
    out["elo_diff"] = diffs
    return out


def score(frame: pd.DataFrame) -> dict:
    d = frame.dropna(subset=["elo_p", "home_points", "away_points"])
    d = d[d["home_points"] != d["away_points"]]  # ties carry no label
    if d.empty:
        return {"n": 0}
    p = d["elo_p"].to_numpy(float)
    y = (d["home_points"] > d["away_points"]).to_numpy(float)
    eps = 1e-6
    return {
        "n": int(len(d)),
        "brier": float(np.mean((p - y) ** 2)),
        "log_loss": float(-np.mean(y * np.log(np.clip(p, eps, 1 - eps))
                                   + (1 - y) * np.log(np.clip(1 - p, eps, 1 - eps)))),
        "acc": float(np.mean((p > 0.5) == (y == 1))),
        "ece": float(expected_calibration_error(p, y)),
    }


def fbs_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["home_division"] == "fbs") & (df["away_division"] == "fbs")]


def fit_elo_per_point(frame: pd.DataFrame) -> float:
    """Elo rating points per point of scoring margin.

    ``EloModel.expected_margin`` divides an Elo difference by this to get a
    spread, so it is the reciprocal of the slope of margin on rating gap.
    Fitted through the origin: a zero rating gap on a neutral field is a
    zero expected margin by construction, and letting the line float would
    absorb home-field advantage a second time.
    """
    d = frame.dropna(subset=["elo_diff", "home_points", "away_points"])
    x = d["elo_diff"].to_numpy(float)
    y = (d["home_points"] - d["away_points"]).to_numpy(float)
    slope = float(np.sum(x * y) / np.sum(x * x))
    return 1.0 / slope


def main() -> None:
    adapter = NCAAFAdapter()
    games = adapter.fetch(DEV_SEASONS[0], EVAL_SEASONS[1])
    dev = games[games["season"].between(*DEV_SEASONS)]
    print(f"development {DEV_SEASONS[0]}-{DEV_SEASONS[1]}: {len(dev)} games "
          f"({len(fbs_only(dev))} FBS-vs-FBS)")

    best, best_brier = None, float("inf")
    results = []
    for k, ha, carry in itertools.product(*GRID.values()):
        cfg = EloConfig(k=k, home_advantage=ha, season_carryover=carry)
        s = score(fbs_only(run_elo(dev, cfg)))
        results.append((s["brier"], k, ha, carry))
        if s["brier"] < best_brier:
            best, best_brier = cfg, s["brier"]
    results.sort()
    print(f"\ngrid: {len(results)} configs scored on FBS-vs-FBS development games")
    print(f"{'brier':>9}  {'k':>5} {'home_adv':>9} {'carryover':>10}")
    for b, k, ha, c in results[:5]:
        print(f"{b:>9.5f}  {k:>5} {ha:>9} {c:>10}")
    print(f"{'...':>9}")
    b, k, ha, c = results[-1]
    print(f"{b:>9.5f}  {k:>5} {ha:>9} {c:>10}   (worst)")

    # elo_per_point is fitted, not searched: it does not affect the win
    # probability at all, only the conversion to a margin.
    dev_run = run_elo(dev, best)
    epp = fit_elo_per_point(fbs_only(dev_run))
    best = replace(best, elo_per_point=round(epp, 2))

    print(f"\nchosen on development data only:")
    for f, v in asdict(best).items():
        print(f"  {f:18} {v}")
    nfl = asdict(EloConfig())
    changed = {f: (nfl[f], v) for f, v in asdict(best).items() if nfl[f] != v}
    print("  differs from the NFL config in: "
          + ", ".join(f"{f} {a}->{b}" for f, (a, b) in changed.items()))

    # --- the frozen config, evaluated once ---------------------------------
    full = run_elo(games, best)
    ev = full[full["season"].between(*EVAL_SEASONS)]
    report = {
        "config": asdict(best),
        "development_seasons": list(DEV_SEASONS),
        "evaluation_seasons": list(EVAL_SEASONS),
        "evaluation": {
            "fbs_vs_fbs": score(fbs_only(ev)),
            "all_fbs_involved": score(ev),
        },
        "market_comparison": None,
        "market_comparison_note": (
            "cfbfastR-data carries no betting lines, so there is no de-vigged "
            "close to score against and no ATS record. This model is unproven "
            "against the market, not shown to beat it."),
    }
    print(f"\nevaluation {EVAL_SEASONS[0]}-{EVAL_SEASONS[1]}, config frozen:")
    for label, s in report["evaluation"].items():
        print(f"  {label:20} n={s['n']:>6}  brier={s['brier']:.5f}  "
              f"logloss={s['log_loss']:.5f}  acc={s['acc']:.4f}  ece={s['ece']:.5f}")
    print("\n  no market comparison: this source has no lines. "
          "Unproven, not beaten.")

    out = Path(__file__).resolve().parents[1] / "data/raw/ncaaf_elo_refit.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
