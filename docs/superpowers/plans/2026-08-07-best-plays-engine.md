# Best-Plays Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a premium "best plays" layer that selects the day's biggest line-shopping edges from the existing board, seals them before kickoff, and grades them on beating the close — all reusing Sooth's existing capture/commit/grade machinery.

**Architecture:** One new module, `engine/best_plays.py`. It reads the `board.json` that `engine/lines.py` already produces, ranks sides by `edge_vs_fair_pts`, converts the top N into `Prediction` objects, seals them with the existing `commit_slate`, and grades them on CLV against our own append-only capture — joined on the shared Odds-API `event_id`, so no cross-adapter ID remapping is needed. Free board and Merkle sealing already exist; this is purely the selection + premium-grading layer.

**Tech Stack:** Python 3 (stdlib + existing engine modules), pytest. No new dependencies.

## Global Constraints

- Premium is graded and marketed ONLY on **"% of plays that beat the closing line."** Never a win/loss record flex, never a win-rate claim. (spec §2)
- Never present a pick as profitable. Never use: guaranteed, lock, risk-free, insider, sure thing. (Sooth charter)
- Never rewrite anything under `data/capture/`, `data/backfill/`, `data/ledger/` — append only. (charter hard-limit #6)
- CLV counts ONLY provenance we control: `own_capture` or `oddsapi_historical_close`. A missing measurement is reported as `None`, never inferred. (grade.py rules)
- Work on `exec/*` branches, never commit to `main` (it is live). (charter hard-limit #8)
- Reuse existing code; add no new dependency. (spec approach A)

**Out of scope for this plan** (separate tracks): the free board UI (exists), premium delivery mechanism, new Discord community, payment processor, and player-props data expansion.

---

## File Structure

- Create: `engine/best_plays.py` — selection, prediction mapping, sealing, CLV grading, CLI.
- Create: `tests/test_best_plays.py` — unit + integration tests.
- Reuse (no change): `engine/lines.py` (produces `board.json` + capture), `engine/commit.py` (`commit_slate`, `verify_slate`), `engine/schema.py` (`Prediction`, `Sport`, `Market`, `american_to_prob`).

### Known interfaces this module consumes (verbatim from the codebase)

- `board.json` shape (from `lines.py collect`): `{"boards": [{"sport": "nfl", "events": [{"id": <odds_api_id>, "home": str, "away": str, "starts": <iso>, "sides": [{"name": <team>, "best_price": int, "best_book": str, "worst_price": int, "n_books": int, "gain_pts": float, "fair_prob": float|None, "fair_price": int|None, "edge_vs_fair_pts": float|None}]}]}]}`
- Capture rows (from `lines.py _capture_rows`, one JSONL per sport per UTC day at `data/capture/<sport>/<YYYY-MM-DD>.jsonl`): `{"observed_at": iso, "event_id": <odds_api_id>, "sport": str, "kickoff": iso, "home": str, "away": str, "book": str, "market": "moneyline", "selection": <team>, "line": None, "price": int, "provenance": "own_capture"}`
- `schema.Prediction(event_id, sport, market, selection, line, probability, model_version, created_at, reference_price=None, reference_line=None, rationale=None)`
- `commit.commit_slate(slate_id: str, sport: str, predictions: list[Prediction], out_dir="data/ledger") -> Commitment` (has `.root`, `.committed_at`); `commit.verify_slate(slate_id, ledger_dir, version=None) -> bool`
- `schema.american_to_prob(price: int) -> float`

---

### Task 1: Select best plays from the board

**Files:**
- Create: `engine/best_plays.py`
- Test: `tests/test_best_plays.py`

**Interfaces:**
- Consumes: `board.json` dict (shape above).
- Produces: `select_plays(board: dict, *, min_edge_pts: float = 1.0, top_n: int = 5) -> list[dict]` — flattened plays sorted by `edge_vs_fair_pts` descending. Each play dict: `{"sport", "event_id", "home", "away", "kickoff", "selection", "best_price", "best_book", "fair_prob", "edge_vs_fair_pts", "gain_pts"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_best_plays.py
from engine.best_plays import select_plays

_BOARD = {
    "boards": [{
        "sport": "nfl",
        "events": [{
            "id": "evt1", "home": "Seattle Seahawks", "away": "New England Patriots",
            "starts": "2026-09-13T17:00:00Z",
            "sides": [
                {"name": "Seattle Seahawks", "best_price": -110, "best_book": "FanDuel",
                 "worst_price": -125, "n_books": 6, "gain_pts": 3.1,
                 "fair_prob": 0.55, "fair_price": -122, "edge_vs_fair_pts": 2.6},
                {"name": "New England Patriots", "best_price": 130, "best_book": "BetMGM",
                 "worst_price": 115, "n_books": 6, "gain_pts": 2.8,
                 "fair_prob": 0.45, "fair_price": 122, "edge_vs_fair_pts": 1.9},
            ],
        }]
    }]
}

def test_select_plays_filters_and_ranks():
    plays = select_plays(_BOARD, min_edge_pts=2.0, top_n=5)
    assert [p["selection"] for p in plays] == ["Seattle Seahawks"]  # 1.9 filtered out
    p = plays[0]
    assert p["event_id"] == "evt1"
    assert p["sport"] == "nfl"
    assert p["best_price"] == -110
    assert p["best_book"] == "FanDuel"
    assert p["fair_prob"] == 0.55
    assert p["kickoff"] == "2026-09-13T17:00:00Z"

def test_select_plays_skips_sides_without_fair():
    board = {"boards": [{"sport": "nfl", "events": [{
        "id": "e", "home": "H", "away": "A", "starts": "2026-09-13T17:00:00Z",
        "sides": [{"name": "H", "best_price": -110, "best_book": "X", "worst_price": -120,
                   "n_books": 2, "gain_pts": 1.0, "fair_prob": None, "fair_price": None,
                   "edge_vs_fair_pts": None}]}]}]}
    assert select_plays(board, min_edge_pts=0.0) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: FAIL with "No module named 'engine.best_plays'" / ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/best_plays.py
"""Premium best plays: select the day's biggest line-shopping edges, seal them
before kickoff, and grade them on beating the close.

The edge math already lives in engine/lines.py (board.json). This module only
selects the sharpest edges, seals them with the existing Merkle machinery, and
grades them on CLV against our own append-only capture. It never presents a play
as profitable and never publishes a win/loss flex - the only headline number is
the share of plays that beat the closing line.
"""
from __future__ import annotations


def select_plays(board: dict, *, min_edge_pts: float = 1.0,
                 top_n: int = 5) -> list[dict]:
    plays: list[dict] = []
    for b in board.get("boards", []):
        sport = b.get("sport", "")
        for e in b.get("events", []):
            for s in e.get("sides", []):
                edge = s.get("edge_vs_fair_pts")
                if edge is None or edge < min_edge_pts:
                    continue
                plays.append({
                    "sport": sport,
                    "event_id": e.get("id", ""),
                    "home": e.get("home", ""),
                    "away": e.get("away", ""),
                    "kickoff": e.get("starts", ""),
                    "selection": s.get("name", ""),
                    "best_price": s.get("best_price"),
                    "best_book": s.get("best_book"),
                    "fair_prob": s.get("fair_prob"),
                    "edge_vs_fair_pts": edge,
                    "gain_pts": s.get("gain_pts"),
                })
    plays.sort(key=lambda p: p["edge_vs_fair_pts"], reverse=True)
    return plays[:top_n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add engine/best_plays.py tests/test_best_plays.py
git commit -m "feat(best-plays): select top edges from the board"
```

---

### Task 2: Convert a play into a sealed Prediction

**Files:**
- Modify: `engine/best_plays.py`
- Test: `tests/test_best_plays.py`

**Interfaces:**
- Consumes: a play dict from Task 1; `schema.Prediction`, `schema.Sport`, `schema.Market`.
- Produces: `play_to_prediction(play: dict) -> Prediction`. Maps: `probability = play["fair_prob"]`, `reference_price = play["best_price"]`, `selection = play["selection"]` (team name, consistent with capture rows), `model_version = "best-plays-v1"`, `created_at = kickoff parsed to UTC datetime`, `market = Market.MONEYLINE`.

- [ ] **Step 1: Write the failing test**

```python
from datetime import timezone
from engine.best_plays import play_to_prediction
from engine.schema import Sport, Market

_PLAY = {
    "sport": "nfl", "event_id": "evt1", "home": "Seattle Seahawks",
    "away": "New England Patriots", "kickoff": "2026-09-13T17:00:00Z",
    "selection": "Seattle Seahawks", "best_price": -110, "best_book": "FanDuel",
    "fair_prob": 0.55, "edge_vs_fair_pts": 2.6, "gain_pts": 3.1,
}

def test_play_to_prediction_maps_fields():
    p = play_to_prediction(_PLAY)
    assert p.event_id == "evt1"
    assert p.sport == Sport.NFL
    assert p.market == Market.MONEYLINE
    assert p.selection == "Seattle Seahawks"
    assert p.probability == 0.55
    assert p.reference_price == -110
    assert p.model_version == "best-plays-v1"
    assert p.created_at.year == 2026 and p.created_at.tzinfo == timezone.utc
    assert "FanDuel" in (p.rationale or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py::test_play_to_prediction_maps_fields -v`
Expected: FAIL with "cannot import name 'play_to_prediction'".

- [ ] **Step 3: Write minimal implementation**

```python
# add to engine/best_plays.py
from datetime import datetime, timezone

from .schema import Market, Prediction, Sport

MODEL_VERSION = "best-plays-v1"


def _parse_utc(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def play_to_prediction(play: dict) -> Prediction:
    return Prediction(
        event_id=str(play["event_id"]),
        sport=Sport(play["sport"]),
        market=Market.MONEYLINE,
        selection=str(play["selection"]),
        line=None,
        probability=float(play["fair_prob"]),
        model_version=MODEL_VERSION,
        created_at=_parse_utc(str(play["kickoff"])),
        reference_price=int(play["best_price"]),
        reference_line=None,
        rationale=(f"line-shop: best price {play['best_price']} at "
                   f"{play['best_book']}, +{play['edge_vs_fair_pts']} pts vs fair"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add engine/best_plays.py tests/test_best_plays.py
git commit -m "feat(best-plays): map a play to a sealed Prediction"
```

---

### Task 3: Seal a day's plays with the existing Merkle machinery

**Files:**
- Modify: `engine/best_plays.py`
- Test: `tests/test_best_plays.py`

**Interfaces:**
- Consumes: plays from Task 1, `play_to_prediction` from Task 2, `commit.commit_slate`, `commit.verify_slate`.
- Produces: `seal_plays(plays: list[dict], slate_id: str, sport: str, out_dir="data/ledger") -> Commitment`. Converts plays to predictions and seals one slate. Raises `ValueError` if `plays` is empty (mirrors `commit_slate`).

- [ ] **Step 1: Write the failing test**

```python
from engine.best_plays import seal_plays
from engine.commit import verify_slate

def test_seal_plays_seals_and_verifies(tmp_path):
    plays = [dict(_PLAY)]
    c = seal_plays(plays, slate_id="2026-09-13-best-nfl", sport="nfl",
                   out_dir=tmp_path)
    assert c.n_predictions == 1
    assert len(c.root) == 64  # sha256 hex
    assert verify_slate("2026-09-13-best-nfl", ledger_dir=tmp_path) is True

def test_seal_plays_empty_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        seal_plays([], slate_id="s", sport="nfl", out_dir=tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -k seal -v`
Expected: FAIL with "cannot import name 'seal_plays'".

- [ ] **Step 3: Write minimal implementation**

```python
# add to engine/best_plays.py
from pathlib import Path

from .commit import Commitment, commit_slate


def seal_plays(plays: list[dict], slate_id: str, sport: str,
               out_dir: Path | str = "data/ledger") -> Commitment:
    if not plays:
        raise ValueError("no plays to seal")
    predictions = [play_to_prediction(p) for p in plays]
    return commit_slate(slate_id, sport, predictions, out_dir=out_dir)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add engine/best_plays.py tests/test_best_plays.py
git commit -m "feat(best-plays): seal a day's plays into the ledger"
```

---

### Task 4: Grade sealed plays on beating the close (CLV)

**Files:**
- Modify: `engine/best_plays.py`
- Test: `tests/test_best_plays.py`

**Interfaces:**
- Consumes: sealed reveal file (via `commit.commitment_history` + reveal JSON), capture rows at `data/capture/<sport>/*.jsonl`, `schema.american_to_prob`.
- Produces: `grade_plays(slate_id, sport, ledger_dir="data/ledger", capture_dir="data/capture") -> dict` returning `{"n_plays", "n_with_clv", "beat_close": int, "beat_close_pct": float|None, "plays": [{"event_id","selection","reference_price","closing_price","clv","beat_close"}]}`. CLV = `american_to_prob(closing) - american_to_prob(reference)`; `beat_close` is `clv > 0`. Closing price = the LATEST `own_capture`/`oddsapi_historical_close` price for `(event_id, selection)` (nearest kickoff). Missing closing price → `clv=None`, excluded from the percentage (never inferred).

Why this join is clean: best plays carry the Odds-API `event_id`, and `lines.py` capture rows carry the SAME `event_id` and the SAME team-name `selection`. So CLV joins directly on `(event_id, selection)` with no nflverse/ESPN ID remapping — unlike `grade.py`, which must bridge three ID spaces for the model slate.

- [ ] **Step 1: Write the failing test**

```python
import json
from engine.best_plays import seal_plays, grade_plays

def _write_capture(capture_dir, sport, rows):
    d = capture_dir / sport
    d.mkdir(parents=True)
    with (d / "2026-09-13.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

def test_grade_plays_computes_beat_close(tmp_path):
    ledger, capture = tmp_path / "ledger", tmp_path / "capture"
    seal_plays([dict(_PLAY)], "2026-09-13-best-nfl", "nfl", out_dir=ledger)
    # We recommended -110 (Seahawks). Close drifted to -140 (shorter price) =>
    # we got the better number => positive CLV => beat the close.
    _write_capture(capture, "nfl", [
        {"observed_at": "2026-09-13T16:59:00Z", "event_id": "evt1", "sport": "nfl",
         "selection": "Seattle Seahawks", "market": "moneyline", "price": -140,
         "provenance": "own_capture"},
    ])
    g = grade_plays("2026-09-13-best-nfl", "nfl",
                    ledger_dir=ledger, capture_dir=capture)
    assert g["n_plays"] == 1
    assert g["n_with_clv"] == 1
    assert g["beat_close"] == 1
    assert g["beat_close_pct"] == 1.0
    assert g["plays"][0]["clv"] > 0

def test_grade_plays_missing_close_is_none(tmp_path):
    ledger, capture = tmp_path / "ledger", tmp_path / "capture"
    seal_plays([dict(_PLAY)], "2026-09-13-best-nfl", "nfl", out_dir=ledger)
    (capture / "nfl").mkdir(parents=True)  # no rows
    g = grade_plays("2026-09-13-best-nfl", "nfl",
                    ledger_dir=ledger, capture_dir=capture)
    assert g["n_with_clv"] == 0
    assert g["beat_close_pct"] is None
    assert g["plays"][0]["clv"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -k grade -v`
Expected: FAIL with "cannot import name 'grade_plays'".

- [ ] **Step 3: Write minimal implementation**

```python
# add to engine/best_plays.py
import glob
import json as _json

from .commit import commitment_history
from .schema import american_to_prob

CLV_PROVENANCE = frozenset({"own_capture", "oddsapi_historical_close"})


def _closing_price(event_id: str, selection: str, sport: str,
                   capture_dir: Path | str) -> int | None:
    """Latest qualifying own-capture price for (event_id, selection)."""
    best_stamp, best_price = "", None
    for path in sorted(glob.glob(str(Path(capture_dir) / sport / "*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if r.get("provenance") not in CLV_PROVENANCE:
                    continue
                if str(r.get("event_id")) != event_id or str(r.get("selection")) != selection:
                    continue
                if r.get("price") is None:
                    continue
                stamp = str(r.get("observed_at") or r.get("snapshot_at") or "")
                if best_price is None or stamp > best_stamp:
                    best_stamp, best_price = stamp, int(r["price"])
    return best_price


def _load_reveal(slate_id: str, ledger_dir: Path | str) -> dict:
    history = commitment_history(slate_id, ledger_dir)
    v = int(history[-1]["version"])
    return _json.loads((Path(ledger_dir) / f"{slate_id}.reveal.v{v}.json").read_text())


def grade_plays(slate_id: str, sport: str, ledger_dir: Path | str = "data/ledger",
                capture_dir: Path | str = "data/capture") -> dict:
    reveal = _load_reveal(slate_id, ledger_dir)
    out = []
    for p in reveal["predictions"]:
        eid, sel = str(p["event_id"]), str(p["selection"])
        ref = p.get("reference_price")
        close = _closing_price(eid, sel, sport, capture_dir)
        clv = (float(american_to_prob(int(close)) - american_to_prob(int(ref)))
               if ref is not None and close is not None else None)
        out.append({
            "event_id": eid, "selection": sel, "reference_price": ref,
            "closing_price": close, "clv": clv,
            "beat_close": (clv > 0) if clv is not None else None,
        })
    with_clv = [r for r in out if r["clv"] is not None]
    beat = sum(1 for r in with_clv if r["beat_close"])
    return {
        "n_plays": len(out),
        "n_with_clv": len(with_clv),
        "beat_close": beat,
        "beat_close_pct": (round(beat / len(with_clv), 4) if with_clv else None),
        "plays": out,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add engine/best_plays.py tests/test_best_plays.py
git commit -m "feat(best-plays): grade sealed plays on beating the close"
```

---

### Task 5: CLI — build the day's best plays and premium payload

**Files:**
- Modify: `engine/best_plays.py`
- Test: `tests/test_best_plays.py`

**Interfaces:**
- Consumes: `board.json` on disk, all functions above.
- Produces: `build(board_path, date, ledger_dir="data/ledger", site_dir="site/public/data", min_edge_pts=1.0, top_n=5) -> dict`. Groups selected plays by sport, seals one slate per sport as `f"{date}-best-{sport}"`, and writes a premium payload `site/public/data/best-plays.json`: `{"generated_at" (=board["generated_at"]), "date", "note", "slates": [{"slate_id","sport","merkle_root","committed_at","plays":[{selection, home, away, best_price, best_book, edge_vs_fair_pts, kickoff}]}]}`. A `__main__` self-check runs `select_plays` on the checked-in board fixture and asserts the pipeline holds. Sports with zero qualifying plays are skipped (never seal an empty slate).

- [ ] **Step 1: Write the failing test**

```python
import json
from engine.best_plays import build

def test_build_writes_payload_and_seals(tmp_path):
    board = {"generated_at": "2026-09-13T12:00:00Z", **_BOARD}
    bp = tmp_path / "board.json"
    bp.write_text(json.dumps(board))
    ledger, site = tmp_path / "ledger", tmp_path / "site"
    doc = build(str(bp), date="2026-09-13", ledger_dir=ledger, site_dir=site,
                min_edge_pts=2.0, top_n=5)
    assert doc["slates"][0]["sport"] == "nfl"
    assert doc["slates"][0]["merkle_root"]
    assert (site / "best-plays.json").exists()
    written = json.loads((site / "best-plays.json").read_text())
    assert written["slates"][0]["plays"][0]["selection"] == "Seattle Seahawks"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -k build -v`
Expected: FAIL with "cannot import name 'build'".

- [ ] **Step 3: Write minimal implementation**

```python
# add to engine/best_plays.py
import argparse


def build(board_path: str, date: str, ledger_dir: Path | str = "data/ledger",
          site_dir: Path | str = "site/public/data", min_edge_pts: float = 1.0,
          top_n: int = 5) -> dict:
    board = _json.loads(Path(board_path).read_text())
    plays = select_plays(board, min_edge_pts=min_edge_pts, top_n=top_n)

    by_sport: dict[str, list[dict]] = {}
    for p in plays:
        by_sport.setdefault(p["sport"], []).append(p)

    slates = []
    for sport, sp_plays in by_sport.items():
        slate_id = f"{date}-best-{sport}"
        c = seal_plays(sp_plays, slate_id, sport, out_dir=ledger_dir)
        slates.append({
            "slate_id": slate_id, "sport": sport, "merkle_root": c.root,
            "committed_at": c.committed_at.isoformat(),
            "plays": [{"selection": p["selection"], "home": p["home"],
                       "away": p["away"], "best_price": p["best_price"],
                       "best_book": p["best_book"],
                       "edge_vs_fair_pts": p["edge_vs_fair_pts"],
                       "kickoff": p["kickoff"]} for p in sp_plays],
        })

    doc = {
        "generated_at": board.get("generated_at", ""),
        "date": date,
        "note": ("Our sharpest line-shopping edges, sealed before kickoff and "
                 "graded on beating the close. Analysis only; we do not accept "
                 "wagers."),
        "slates": slates,
    }
    sd = Path(site_dir)
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "best-plays.json").write_text(_json.dumps(doc, indent=2))
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="site/public/data/board.json")
    ap.add_argument("--date", required=True)  # UTC YYYY-MM-DD
    ap.add_argument("--ledger", default="data/ledger")
    ap.add_argument("--site", default="site/public/data")
    ap.add_argument("--min-edge-pts", type=float, default=1.0)
    ap.add_argument("--top-n", type=int, default=5)
    a = ap.parse_args()
    doc = build(a.board, a.date, a.ledger, a.site, a.min_edge_pts, a.top_n)
    for s in doc["slates"]:
        print(f"{s['sport']:<4} {len(s['plays'])} plays  root {s['merkle_root'][:12]}…")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full test file and the self-check**

Run: `.venv/bin/python -m pytest tests/test_best_plays.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add engine/best_plays.py tests/test_best_plays.py
git commit -m "feat(best-plays): CLI to build and seal the daily premium payload"
```

---

## Self-Review

**1. Spec coverage:**
- §1 architecture (one module on existing engine) → Tasks 1–5, no new deps. ✓
- §2 two edges + honest number → edges read from board (`edge_vs_fair_pts`, `gain_pts`, Task 1); "% beat the close" is the only graded number (Task 4). ✓
- §2 sealed before kickoff → `seal_plays` via `commit_slate` (Task 3). ✓
- §3 premium sealed top plays payload → `best-plays.json` (Task 5). Free board already exists in `lines.py` (out of scope, noted). ✓
- §4 props gated → the module is sport-agnostic; props flip live by adding their sport to `lines.py SPORTS` and clearing the beat-close bar. No code change here forces props live. ✓
- §5 community, §6 payments, §7 timeline → out of scope (separate tracks), stated up front. ✓

**2. Placeholder scan:** No TBD/TODO; every step has runnable code and a concrete command. ✓

**3. Type consistency:** `select_plays` → `play_to_prediction` → `seal_plays` → `grade_plays`/`build` all pass the same play-dict keys and `event_id`/`selection` join keys; `MODEL_VERSION`, `CLV_PROVENANCE`, `_parse_utc`, `_closing_price` defined once and reused. `commit_slate`/`verify_slate`/`Prediction`/`american_to_prob` signatures match the codebase. ✓

## Open items for a later plan (not this one)
- Win/loss settlement per sport (secondary to CLV; needs a results source per sport).
- Multi-version reveal handling in `grade_plays` if a slate is re-sealed (currently grades latest version).
- Premium delivery (gated page/channel), Discord community, payment processor, props data expansion.
