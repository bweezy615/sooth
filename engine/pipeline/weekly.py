"""Weekly slate: predict with BOTH models, calibrate, cap, commit, publish.

Two numbers are published for every game, and the distinction is the honest
part:

  independent  Elo + opponent-aware EPA ratings + rest. Knows nothing about
               the betting line. This is our actual opinion. It is measurably
               worse than the market (Brier 0.2216 vs 0.2106) and it is the
               only number that can disagree with the market informatively.

  consensus    The same features PLUS the de-vigged market probability. The
               sharpest output we can produce (Brier 0.2140 vs the market's
               0.2106 on eval B) - but it mostly reproduces the market, so
               presenting it as "our prediction" would look impressive while
               carrying almost no independent information.

Publishing only the consensus would be the industry's standard dishonesty:
market-following dressed as insight. Publishing only the independent number
would throw away our best-calibrated estimate. So both ship, labelled, and
the methodology page explains which is which.

Both are sealed in the same Merkle commitment. Neither can be quietly
retracted later.

    python -m engine.pipeline.weekly --season 2026 --week 1
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ..adapters.nfl import NFLAdapter
from ..calibrate import Calibrator
from ..commit import commit_slate
from ..features import attach_carry_forward, build_team_ratings, load_team_weeks
from ..models.ensemble import BASE_FEATURES, MARKET_FEATURE, build_frame, _logit
from ..models.elo import EloConfig, EloModel
from ..schema import (Market, Prediction, Sport, american_to_prob, devig,
                      prob_to_american)

# The top confidence band is too thin to trust (n=12 in the current record)
# and an earlier larger run measured ~8 pts of overconfidence there, so we cap
# rather than publish a number we cannot substantiate.
CONFIDENCE_CAP = 0.85
MODEL_INDEPENDENT = "elo+epa-v1+iso"
MODEL_CONSENSUS = "elo+epa+market-v1+iso"


def _fit_models(hist: pd.DataFrame):
    """Fit both models and their calibrators on all completed history."""
    ind_feats, con_feats = BASE_FEATURES, BASE_FEATURES + [MARKET_FEATURE]

    ind_train = hist.dropna(subset=ind_feats + ["home_won"])
    con_train = hist.dropna(subset=con_feats + ["home_won"])

    ind = LogisticRegression(max_iter=2000).fit(
        ind_train[ind_feats], ind_train["home_won"])
    con = LogisticRegression(max_iter=2000).fit(
        con_train[con_feats], con_train["home_won"])

    # Calibrators fitted on in-sample fits are optimistic, but the walk-forward
    # backtest already established the honest calibration numbers we publish.
    ind_cal = Calibrator().fit(
        ind.predict_proba(ind_train[ind_feats])[:, 1],
        ind_train["home_won"].to_numpy(float), through_season=0)
    con_cal = Calibrator().fit(
        con.predict_proba(con_train[con_feats])[:, 1],
        con_train["home_won"].to_numpy(float), through_season=0)

    return (ind, ind_cal, ind_feats), (con, con_cal, con_feats)


def _elo_through(adapter: NFLAdapter, season: int, week: int) -> EloModel:
    df = adapter.games
    done = df[df["home_score"].notna() & df["away_score"].notna()].sort_values(
        ["season", "week", "gameday"])
    prior = done[(done["season"] < season)
                 | ((done["season"] == season)
                    & (pd.to_numeric(done["week"], errors="coerce") < week))]
    model = EloModel(config=EloConfig())
    for _, r in prior.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        rd = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce")
        model.update(home, away,
                     float(r["home_score"]) - float(r["away_score"]),
                     neutral=str(r.get("location", "Home")) != "Home",
                     rest_diff=0.0 if pd.isna(rd) else float(rd),
                     season=int(r["season"]))
    return model


# --------------------------------------------------------------------------
# Pick-engine payloads (docs/pick-engine-plan.md, Step 1).
#
# One slate becomes two files:
#   data/pro/{slate_id}.pro.json      the full slate, served only by /api/picks
#   site/public/data/{slate_id}.json  the public file — the full slate
#
# THE SLATE IS NO LONGER WITHHELD UNTIL KICKOFF (changed 2026-08-22).
#
# The redaction here existed to sell TIMING: Pro bought the slate at seal time,
# everyone else waited for first kickoff. The paid tier was deleted, so the
# lock had nothing left to sell and was withholding for its own sake.
#
# It was never a proof mechanism, and it is worth being precise about why,
# because the opposite was claimed on the site for a while. Commit-reveal
# integrity rests on ONE thing: hash(picks) published, and externally
# timestamped, BEFORE the event. Anyone can then check hash(revealed) against
# the committed root. The reveal TIME is irrelevant to that proof as long as
# the commit preceded the games. The 2026-W01 root was anchored to a public
# GitHub commit on 2026-08-06 for games starting 2026-09-10; revealing on
# 08-22 still proves the picks existed five weeks early.
#
# The reveal file has in fact been public the whole time —
# {slate_id}.reveal.json carries all 32 predictions in the clear as the Merkle
# leaf set. So the redaction was not even hiding the picks; it was declining
# to render them on one page while publishing them on another.
# --------------------------------------------------------------------------

def _pickengine_payloads(root: Path, payload: dict) -> dict:
    """Write the pro payload and return the redacted public games list."""
    now = datetime.now(timezone.utc)
    slate_id = payload["slate_id"]

    # Best prices join by game_id when the board window has NFL priced;
    # earlier than that the fields are honest nulls, never invented.
    try:
        bl = json.loads(
            (root / "site/public/data/best_lines.json").read_text())
        best = {g["game_id"]: g for g in bl.get("games", [])}
    except (OSError, json.JSONDecodeError):
        best = {}

    pro_games, ranked = [], []
    for g in payload["games"]:
        ind, mkt = g["independent"], g["market_prob"]
        home_basis = ind["prob"] if ind["pick"] == g["home"] else 1 - ind["prob"]
        divergence = (None if mkt is None
                      else round(abs(home_basis - mkt), 4))
        b = best.get(g["game_id"], {})
        pro_games.append({
            **g,
            "divergence": divergence,
            "best_price": b.get("best_price"),
            "best_book": b.get("best_book"),
            "n_books": b.get("n_books"),
            "edge_pts": b.get("edge_pts"),
            "quotes": b.get("quotes"),
        })
        ranked.append((divergence if divergence is not None else -1.0,
                       g["game_id"]))

    ranked.sort(reverse=True)
    rank_of = {gid: i + 1 for i, (_, gid) in enumerate(ranked)}

    pro_doc = {
        k: payload[k] for k in
        ("slate_id", "sport", "season", "week", "status", "models",
         "confidence_cap", "merkle_root", "committed_at",
         "earliest_kickoff", "n_predictions", "disclaimer")
    }
    pro_doc["games"] = sorted(
        pro_games, key=lambda g: rank_of[g["game_id"]])
    pro_doc["reveal"] = f"/data/{slate_id}.reveal.json"

    # The ledger repo is public (that IS the timestamp anchor), so the Pro
    # payload lands as AES-256-GCM ciphertext — the committed blob is itself a
    # timestamped commitment to the Pro slate. A plaintext sidecar carries
    # ONLY the teaser fields the locked view needs.
    from .. import prosec
    pro_dir = root / "data/pro"
    pro_dir.mkdir(parents=True, exist_ok=True)
    body = prosec.encrypt(json.dumps(pro_doc, separators=(",", ":")))
    (pro_dir / f"{slate_id}.pro.enc").write_text(body)
    (pro_dir / "latest.pro.enc").write_text(body)    # /api/picks reads this
    top = pro_doc["games"][0] if pro_doc["games"] else None
    (pro_dir / "latest.meta.json").write_text(json.dumps({
        "slate_id": slate_id,
        "game_count": len(pro_doc["games"]),
        "sealed_at": payload["committed_at"],
        "merkle_root": payload["merkle_root"],
        "earliest_kickoff": payload["earliest_kickoff"],
        "top_divergence_matchup": (f"{top['away']} at {top['home']}"
                                   if top else None),
    }, indent=2))

    # The full slate, published with the commitment. `locked` stays in the
    # payload as False so every consumer keeps its shape.
    public_games = []
    for g in pro_doc["games"]:
        g = dict(g)
        g["divergence_rank"] = rank_of[g["game_id"]]
        public_games.append(g)
    return {"locked": False, "unlocks_at": payload["earliest_kickoff"],
            "games": public_games}


def build_slate(season: int, week: int, out_root: Path | str = ".") -> dict:
    root = Path(out_root)
    adapter = NFLAdapter(cache_dir=root / "data/raw")
    adapter.fetch(force=True)

    hist = build_frame(1999, season - 1 if week == 1 else season)
    (ind, ind_cal, ind_feats), (con, con_cal, con_feats) = _fit_models(hist)

    ratings = build_team_ratings(load_team_weeks(1999, season))
    elo = _elo_through(adapter, season, week)

    df = adapter.games
    slate = df[(df["season"] == season)
               & (pd.to_numeric(df["week"], errors="coerce") == week)
               & df["home_score"].isna()].copy()
    if slate.empty:
        raise SystemExit(f"no unplayed games for {season} week {week}")

    slate = attach_carry_forward(slate, ratings, season, week)

    rows, predictions, display = [], [], []
    now = datetime.now(timezone.utc)

    for _, r in slate.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        neutral = str(r.get("location", "Home")) != "Home"
        rd = pd.to_numeric(r.get("home_rest"), errors="coerce") - pd.to_numeric(
            r.get("away_rest"), errors="coerce")
        rd = 0.0 if pd.isna(rd) else float(rd)

        elo_p = elo.expected(home, away, neutral=neutral, rest_diff=rd,
                             season=season)

        hml, aml = r.get("home_moneyline"), r.get("away_moneyline")
        mkt_home = np.nan
        if pd.notna(hml) and pd.notna(aml):
            mkt_home, _ = devig(american_to_prob(int(hml)),
                                american_to_prob(int(aml)))

        feat = {
            "elo_logit": float(_logit(np.array([elo_p]))[0]),
            "epa_edge": r.get("epa_edge"), "off_diff": r.get("off_diff"),
            "def_diff": r.get("def_diff"), "rest_diff": rd,
            "div_game": pd.to_numeric(r.get("div_game"), errors="coerce") or 0,
            "is_playoff": 0,
            "market_logit": float(_logit(np.array([
                mkt_home if pd.notna(mkt_home) else 0.5]))[0]),
        }
        X = pd.DataFrame([feat])
        if X[ind_feats].isna().any(axis=None):
            continue

        p_ind = float(ind_cal.transform(ind.predict_proba(X[ind_feats])[:, 1])[0])
        p_con = float(con_cal.transform(con.predict_proba(X[con_feats])[:, 1])[0])

        kickoff = adapter._kickoff(r)
        eid = str(r["game_id"])

        for label, prob, version in (("independent", p_ind, MODEL_INDEPENDENT),
                                     ("consensus", p_con, MODEL_CONSENSUS)):
            pick_home = prob >= 0.5
            conf = min(prob if pick_home else 1 - prob, CONFIDENCE_CAP)
            predictions.append(Prediction(
                event_id=eid, sport=Sport.NFL, market=Market.MONEYLINE,
                selection="side_a" if pick_home else "side_b", line=None,
                probability=round(conf, 4), model_version=version,
                created_at=kickoff,
                reference_price=(int(hml) if pick_home and pd.notna(hml)
                                 else int(aml) if pd.notna(aml) else None),
                reference_line=(float(r["spread_line"])
                                if pd.notna(r.get("spread_line")) else None),
                rationale=f"{label}: elo {elo.rating(home):.0f} vs "
                          f"{elo.rating(away):.0f}, epa_edge {r.get('epa_edge'):.3f}",
            ))

        ip, cp = min(max(p_ind, 1 - CONFIDENCE_CAP), CONFIDENCE_CAP), \
                 min(max(p_con, 1 - CONFIDENCE_CAP), CONFIDENCE_CAP)
        display.append({
            "game_id": eid, "kickoff": kickoff.isoformat(),
            "home": home, "away": away,
            "independent": {
                "pick": home if ip >= 0.5 else away,
                "prob": round(max(ip, 1 - ip), 4),
                "fair_odds": prob_to_american(round(max(ip, 1 - ip), 4)),
            },
            "consensus": {
                "pick": home if cp >= 0.5 else away,
                "prob": round(max(cp, 1 - cp), 4),
                "fair_odds": prob_to_american(round(max(cp, 1 - cp), 4)),
            },
            "market_prob": (None if pd.isna(mkt_home)
                            else round(float(mkt_home), 4)),
            "spread_line": (float(r["spread_line"])
                            if pd.notna(r.get("spread_line")) else None),
            "models_disagree": (ip >= 0.5) != (cp >= 0.5),
            "independent_vs_market": (
                None if pd.isna(mkt_home) else bool((mkt_home >= 0.5) != (ip >= 0.5))),
        })

    slate_id = f"{season}-W{week:02d}-nfl"
    commitment = commit_slate(slate_id, "nfl", predictions,
                              out_dir=root / "data/ledger")

    # Backtest metadata comes from the regenerated figures file, never from
    # hand-typed constants — the one hard rule this project has.
    _fig = json.loads((root / "site/content/_figures.json").read_text())
    _evb = _fig["evaluation_b"]["results"]
    payload = {
        "slate_id": slate_id, "sport": "nfl", "season": season, "week": week,
        "status": "committed",
        "models": {
            "independent": {
                "version": MODEL_INDEPENDENT,
                "description": "Elo + opponent-aware EPA + rest. Does not see "
                               "the betting line. This is our own opinion.",
                "backtest_brier": _evb["independent"]["brier"],
                "backtest_ece": _evb["independent"]["ece"],
            },
            "consensus": {
                "version": MODEL_CONSENSUS,
                "description": "The same features plus the de-vigged market "
                               "probability. Best calibrated, but largely "
                               "reproduces the market.",
                "backtest_brier": _evb["consensus"]["brier"],
                "backtest_ece": _evb["consensus"]["ece"],
            },
        },
        "confidence_cap": CONFIDENCE_CAP,
        "merkle_root": commitment.root,
        "committed_at": commitment.committed_at.isoformat(),
        "earliest_kickoff": commitment.earliest_kickoff.isoformat(),
        "n_predictions": len(predictions),
        "games": display,
        "disclaimer": (
            "Analysis and entertainment only. We do not accept wagers. Our "
            "backtest does not beat the closing market - see /methodology."),
    }

    # Pro payload written first; the public file carries the redacted games.
    public = _pickengine_payloads(root, payload)
    site_payload = dict(payload)
    site_payload["games"] = public["games"]
    site_payload["locked"] = public["locked"]
    site_payload["unlocks_at"] = public["unlocks_at"]

    site_dir = root / "site/public/data"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / f"{slate_id}.json").write_text(json.dumps(site_payload, indent=2))

    # The /verify walkthrough curls the un-versioned commitment and reveal.
    # Re-sealing MUST refresh both, or the published pair stops matching and
    # the flagship check fails for anyone who runs it.
    ledger_dir = root / "data/ledger"
    versions = sorted(ledger_dir.glob(f"{slate_id}.commitment.v*.json"))
    if versions:
        (site_dir / f"{slate_id}.commitment.json").write_text(
            versions[-1].read_text())
    reveals = sorted(ledger_dir.glob(f"{slate_id}.reveal.v*.json"))
    if reveals:
        (site_dir / f"{slate_id}.reveal.json").write_text(
            reveals[-1].read_text())

    # The board's Picks tab discovers slates through this index.
    idx_path = site_dir / "slates.json"
    try:
        idx = json.loads(idx_path.read_text())
    except (OSError, json.JSONDecodeError):
        idx = {"slates": []}
    if slate_id not in idx["slates"]:
        idx["slates"].append(slate_id)
    idx["latest"] = slate_id
    idx_path.write_text(json.dumps(idx))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    args = ap.parse_args()
    p = build_slate(args.season, args.week)
    print(f"slate       : {p['slate_id']}")
    print(f"games       : {len(p['games'])}")
    print(f"predictions : {p['n_predictions']} (2 models x {len(p['games'])} games)")
    print(f"merkle root : {p['merkle_root']}")
    print()
    hdr = f"{'matchup':<12} {'independent':<18} {'consensus':<18} {'mkt':>6}"
    print(hdr); print("-" * len(hdr))
    for g in p["games"]:
        i, c = g["independent"], g["consensus"]
        mp = "  n/a" if g["market_prob"] is None else f"{g['market_prob']:.3f}"
        flag = "  <-- models differ" if g["models_disagree"] else ""
        print(f"{g['away']+' @ '+g['home']:<12} "
              f"{i['pick']+' '+format(i['prob'],'.3f'):<18} "
              f"{c['pick']+' '+format(c['prob'],'.3f'):<18} {mp:>6}{flag}")


if __name__ == "__main__":
    main()
