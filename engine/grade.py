"""Grade a revealed slate. This is what turns the ledger from a promise into
a record.

Sealing predictions proves we did not change them. It says nothing about
whether they were any good. Grading closes that loop, and until it exists the
ledger is only half the product.

Two rules make this honest rather than decorative:

1. **Only provenance we control counts toward closing-line value.** A CLV
   figure computed against someone else's undocumented "closing" number is a
   guess wearing a lab coat. Qualifying rows are ``own_capture`` (we watched
   the price ourselves, timestamped) and ``oddsapi_historical_close`` (we paid
   for it and hold it). Everything else grades on result only, and the output
   says so explicitly rather than silently omitting it.

2. **A missing measurement is reported, never inferred.** If we lack a
   qualifying pre-close reference price for a game, CLV for that game is
   ``None`` and the slate reports partial coverage. Filling that gap with the
   nearest available number is how a track record quietly becomes fiction.

    python -m engine.grade --slate 2026-W01-nfl
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .adapters.nfl import NFLAdapter
from .commit import commitment_history
from .schema import american_to_prob, devig

# Only these provenances may contribute to a published CLV number.
CLV_PROVENANCE = frozenset({"own_capture", "oddsapi_historical_close"})


@dataclass
class GradedPrediction:
    event_id: str
    model_version: str
    selection: str
    probability: float
    won: bool | None            # None if the game is not settled
    brier: float | None
    reference_price: int | None  # price we saw when we predicted
    closing_price: int | None    # qualifying close, if we hold one
    clv: float | None            # our implied prob minus closing implied prob
    clv_blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SlateGrade:
    slate_id: str
    version: int
    merkle_root: str
    n_predictions: int
    n_settled: int
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    clv_coverage: float = 0.0
    clv_note: str = ""
    predictions: list[GradedPrediction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["predictions"] = [p.to_dict() for p in self.predictions]
        return d

    def summary(self) -> str:
        lines = [
            f"slate            : {self.slate_id} (v{self.version})",
            f"merkle root      : {self.merkle_root}",
            f"predictions      : {self.n_predictions}",
            f"settled          : {self.n_settled}",
            "",
        ]
        if not self.by_model:
            lines.append("nothing settled yet - nothing to grade.")
            return "\n".join(lines)
        hdr = f"{'model':<26} {'record':>10} {'win%':>7} {'brier':>8} {'CLV':>9}"
        lines += [hdr, "-" * len(hdr)]
        for name, m in sorted(self.by_model.items()):
            clv = "n/a" if m["mean_clv"] is None else f"{m['mean_clv']:+.4f}"
            lines.append(
                f"{name:<26} {m['record']:>10} {m['win_pct']:>7.4f} "
                f"{m['brier']:>8.5f} {clv:>9}")
        lines += ["", f"CLV coverage     : {self.clv_coverage:.1%}", self.clv_note]
        return "\n".join(lines)


def load_reveal(slate_id: str, ledger_dir: Path | str = "data/ledger",
                version: int | None = None) -> tuple[dict, int]:
    d = Path(ledger_dir)
    history = commitment_history(slate_id, d)
    if history:
        target = (history[-1] if version is None
                  else next(c for c in history
                            if int(c.get("version", 0)) == version))
        v = int(target["version"])
        return json.loads((d / f"{slate_id}.reveal.v{v}.json").read_text()), v
    return json.loads((d / f"{slate_id}.reveal.json").read_text()), 1


def _results_for(event_ids: set[str], adapter: NFLAdapter) -> dict[str, float]:
    """event_id -> home margin, for settled games only."""
    df = adapter.games
    sub = df[df["game_id"].astype(str).isin(event_ids)
             & df["home_score"].notna() & df["away_score"].notna()]
    return {str(r["game_id"]): float(r["home_score"]) - float(r["away_score"])
            for _, r in sub.iterrows()}


def _game_id_index(adapter: NFLAdapter) -> dict[tuple[int, str, str], str]:
    """(season, home_abbr, away_abbr) -> nflverse game_id."""
    df = adapter.games
    return {
        (int(r["season"]), str(r["home_team"]), str(r["away_team"])): str(r["game_id"])
        for _, r in df.iterrows()
        if pd.notna(r.get("season"))
    }


def _resolve_game_id(row: dict, index: dict[tuple[int, str, str], str]) -> str | None:
    """Map an odds row onto a nflverse game_id.

    THREE ID SPACES exist in this project and none of them agree:
      - predictions use nflverse ``game_id``   (e.g. 2026_01_NE_SEA)
      - live capture rows carry ESPN event ids (e.g. 401872656)
      - backfill rows carry Odds API event ids (32-char hashes)

    Keying CLV on the raw event_id therefore matches nothing and reports
    "CLV unavailable" forever - a silent zero that looks like a data gap
    rather than a bug. Team names plus season are the only stable join.
    """
    from .closing import TEAM_MAP

    home = TEAM_MAP.get(str(row.get("home", "")), str(row.get("home", "")))
    away = TEAM_MAP.get(str(row.get("away", "")), str(row.get("away", "")))
    season = row.get("season")
    if season is None:
        return None
    return index.get((int(season), home, away))


def _closing_prices(event_ids: set[str], adapter: NFLAdapter,
                    capture_glob: str = "data/capture/nfl/*.jsonl",
                    backfill_glob: str = "data/backfill/nfl_*.jsonl"
                    ) -> dict[tuple[str, str], int]:
    """(nflverse game_id, selection) -> closing American price, provenance-gated.

    Reads only rows whose provenance we control. The latest qualifying
    observation per (game, selection) wins, since that is closest to kickoff.
    """
    import glob

    index = _game_id_index(adapter)
    best: dict[tuple[str, str], tuple[str, int]] = {}
    for pattern in (capture_glob, backfill_glob):
        for path in sorted(glob.glob(pattern)):
            with open(path) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if r.get("provenance") not in CLV_PROVENANCE:
                        continue
                    if r.get("market") != "moneyline":
                        continue
                    gid = _resolve_game_id(r, index)
                    if gid is None or gid not in event_ids:
                        continue
                    price = r.get("price")
                    if price is None:
                        continue
                    stamp = str(r.get("observed_at") or r.get("snapshot_at") or "")
                    key = (gid, str(r.get("selection")))
                    if key not in best or stamp > best[key][0]:
                        best[key] = (stamp, int(price))
    return {k: v[1] for k, v in best.items()}


def grade_slate(slate_id: str, ledger_dir: Path | str = "data/ledger",
                version: int | None = None,
                out_dir: Path | str | None = None) -> SlateGrade:
    reveal, v = load_reveal(slate_id, ledger_dir, version)
    preds = reveal["predictions"]
    event_ids = {str(p["event_id"]) for p in preds}

    adapter = NFLAdapter()
    margins = _results_for(event_ids, adapter)
    closes = _closing_prices(event_ids, adapter)

    graded: list[GradedPrediction] = []
    for p in preds:
        eid = str(p["event_id"])
        sel = str(p["selection"])
        prob = float(p["probability"])
        margin = margins.get(eid)

        if margin is None or margin == 0:
            won = None
            brier = None
        else:
            home_won = margin > 0
            won = (sel == "side_a") == home_won
            brier = float((prob - (1.0 if won else 0.0)) ** 2)

        ref = p.get("reference_price")
        close = closes.get((eid, sel))
        clv = None
        reason = None
        if ref is None:
            reason = "no reference price recorded at prediction time"
        elif close is None:
            reason = ("no qualifying closing price held for this selection "
                      "(provenance must be own_capture or "
                      "oddsapi_historical_close)")
        else:
            # Positive CLV: we took a price implying a lower probability than
            # the close, i.e. we got a better number than the market settled on.
            clv = float(american_to_prob(int(close)) - american_to_prob(int(ref)))

        graded.append(GradedPrediction(
            event_id=eid, model_version=str(p["model_version"]),
            selection=sel, probability=prob, won=won, brier=brier,
            reference_price=ref, closing_price=close, clv=clv,
            clv_blocked_reason=reason,
        ))

    by_model: dict[str, dict[str, Any]] = {}
    for name in sorted({g.model_version for g in graded}):
        rows = [g for g in graded if g.model_version == name and g.won is not None]
        if not rows:
            continue
        wins = sum(1 for g in rows if g.won)
        clvs = [g.clv for g in rows if g.clv is not None]
        by_model[name] = {
            "n": len(rows),
            "record": f"{wins}-{len(rows) - wins}",
            "win_pct": round(wins / len(rows), 4),
            "brier": round(float(np.mean([g.brier for g in rows])), 5),
            "mean_clv": (round(float(np.mean(clvs)), 5) if clvs else None),
            "clv_n": len(clvs),
        }

    settled = [g for g in graded if g.won is not None]
    with_clv = [g for g in settled if g.clv is not None]
    coverage = (len(with_clv) / len(settled)) if settled else 0.0
    note = ("CLV computed only from prices we captured ourselves or paid for. "
            if with_clv else
            "CLV unavailable: we hold no qualifying pre-close reference price "
            "for these games. Reported as unavailable rather than estimated.")

    grade = SlateGrade(
        slate_id=slate_id, version=v,
        merkle_root=str(reveal.get("merkle_root", "")),
        n_predictions=len(preds), n_settled=len(settled),
        by_model=by_model, clv_coverage=round(coverage, 4), clv_note=note,
        predictions=graded,
    )

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{slate_id}.graded.v{v}.json").write_text(
            json.dumps(grade.to_dict(), indent=2, default=str))
    return grade


def publish(grade: SlateGrade, site_dir: Path | str = "site/public/data",
            names_from: Path | str | None = None,
            names: dict[str, dict] | None = None) -> Path:
    """Write the public graded artifact (pick-engine plan, Step 4).

    Per-pick rows carry matchup names so the site never has to join files.
    Names come from the pro payload (or the public slate file — redaction
    keeps home/away visible), and a missing name degrades to the event id,
    never to a crash. Missing closes stay null with their reason verbatim.
    """
    slate_id = grade.slate_id
    names = dict(names or {})
    candidates = ([Path(names_from)] if names_from else []) + [
        Path("data/pro") / f"{slate_id}.pro.enc",
        Path("site/public/data") / f"{slate_id}.json",
    ]
    if not names:
        for c in candidates:
            try:
                text = c.read_text()
                if c.suffix == ".enc":
                    from . import prosec
                    text = prosec.decrypt(text)
                for g in json.loads(text).get("games", []):
                    names[str(g["game_id"])] = g
                break
            except Exception:
                continue  # names survive in the public file either way

    rows = []
    for g in grade.predictions:
        meta = names.get(g.event_id, {})
        home, away = meta.get("home", "home"), meta.get("away", "away")
        rows.append({
            "event_id": g.event_id,
            "model": g.model_version,
            "matchup": f"{away} at {home}",
            "pick": home if g.selection == "side_a" else away,
            "prob": g.probability,
            "won": g.won,
            "brier": g.brier,
            "reference_price": g.reference_price,
            "closing_price": g.closing_price,
            "clv": g.clv,
            "clv_blocked_reason": g.clv_blocked_reason,
            "kickoff": meta.get("kickoff"),
        })

    doc = grade.to_dict()
    doc["picks"] = rows
    doc["published_at"] = datetime.now(timezone.utc).isoformat()
    out = Path(site_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slate_id}.graded.json"
    path.write_text(json.dumps(doc, indent=2, default=str))
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slate", required=True)
    ap.add_argument("--ledger", default="data/ledger")
    ap.add_argument("--version", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--publish", action="store_true",
                    help="also write site/public/data/{slate}.graded.json")
    args = ap.parse_args()
    grade = grade_slate(args.slate, args.ledger, args.version, args.out)
    print(grade.summary())
    if args.publish:
        print(f"published      : {publish(grade)}")


if __name__ == "__main__":
    main()
