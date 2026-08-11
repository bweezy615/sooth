"""Best-lines generator — joins slate picks with board prices.

Reads the latest weekly slate for independent model picks/probs and board.json
for real prices, joins on (home_abbr, away_abbr), and writes best_lines.json.

Zero Odds-API credits — consumes files engine.lines already wrote.

    python -m engine.best_lines
    python -m engine.best_lines --demo
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .closing import TEAM_MAP
from .schema import american_to_prob

DATA = Path("site/public/data")

SOURCE = "the-odds-api, US books, moneyline"
NOTE = (
    "Best available price for the side our model prefers. "
    "Shopping the best number is +EV on its own, whatever the pick."
)


def _load_slate(data_dir: Path) -> tuple[str, list[dict]]:
    """Return (slate_id, games) from the latest slate."""
    slates = json.loads((data_dir / "slates.json").read_text())
    slate_id: str = slates["latest"]
    slate = json.loads((data_dir / f"{slate_id}.json").read_text())
    return slate_id, slate["games"]


def _load_nfl_events(data_dir: Path) -> list[dict]:
    """Return NFL events from board.json, or [] if no NFL board."""
    board = json.loads((data_dir / "board.json").read_text())
    for b in board.get("boards", []):
        if b.get("sport") == "nfl":
            return b.get("events", [])
    return []


def _abbrev(full_name: str) -> str | None:
    return TEAM_MAP.get(full_name)


def generate(data_dir: Path = DATA) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    slate_id, slate_games = _load_slate(data_dir)
    nfl_events = _load_nfl_events(data_dir)

    # Build lookup: (home_abbr, away_abbr) -> board event
    board_index: dict[tuple[str, str], dict] = {}
    for ev in nfl_events:
        ha = _abbrev(ev.get("home", ""))
        aa = _abbrev(ev.get("away", ""))
        if ha and aa:
            board_index[(ha, aa)] = ev

    games = []
    for sg in slate_games:
        home_abbr = sg.get("home", "")
        away_abbr = sg.get("away", "")
        ind = sg.get("independent", {})
        pick = ind.get("pick") or sg.get("pick")  # fallback for older slates
        our_prob = ind.get("prob") or sg.get("prob")
        game_id = sg.get("game_id", "")
        kickoff = sg.get("kickoff", "")

        ev = board_index.get((home_abbr, away_abbr))
        if ev is None:
            continue  # not in board window yet

        # Find the side whose name maps to the slate pick
        matched_side = None
        for side in ev.get("sides", []):
            if _abbrev(side.get("name", "")) == pick:
                matched_side = side
                break

        if matched_side is None:
            continue

        games.append({
            "game_id": game_id,
            "away": away_abbr,
            "home": home_abbr,
            "kickoff": kickoff,
            "pick": pick,
            "our_prob": our_prob,
            "best_price": matched_side["best_price"],
            "best_book": matched_side["best_book"],
            "worst_price": matched_side["worst_price"],
            "worst_book": matched_side["worst_book"],
            "n_books": matched_side["n_books"],
            "edge_pts": matched_side["gain_pts"],
            "quotes": matched_side["quotes"],
        })

    # Top-level aggregates
    edge_vals = [g["edge_pts"] for g in games] if games else []
    n_books_vals = [g["n_books"] for g in games] if games else []

    doc = {
        "generated_at": now,
        "slate_id": slate_id,
        "source": SOURCE,
        "note": NOTE,
        "games": games,
        "avg_edge_pts": round(sum(edge_vals) / len(edge_vals), 2) if edge_vals else 0,
        "max_edge_pts": round(max(edge_vals), 2) if edge_vals else 0,
        "n_books": max(n_books_vals) if n_books_vals else 0,
    }

    # Atomic write (mirrors lines.py pattern)
    out = data_dir / "best_lines.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1))
    os.replace(tmp, out)

    return doc


# ---------------------------------------------------------------------------
# Self-check / demo
# ---------------------------------------------------------------------------

def _validate_schema(doc: dict) -> None:
    top_keys = {"generated_at", "slate_id", "source", "note", "games",
                 "avg_edge_pts", "max_edge_pts", "n_books"}
    assert top_keys <= set(doc.keys()), f"missing top-level keys: {top_keys - set(doc.keys())}"
    game_keys = {"game_id", "away", "home", "kickoff", "pick", "our_prob",
                 "best_price", "best_book", "worst_price", "worst_book",
                 "n_books", "edge_pts", "quotes"}
    for g in doc["games"]:
        assert game_keys <= set(g.keys()), f"missing game keys: {game_keys - set(g.keys())}"
        for q in g["quotes"]:
            assert {"book", "price"} <= set(q.keys()), f"bad quote: {q}"


def demo() -> None:
    """Run against real data, then exercise the join path with a synthetic event."""
    import tempfile, shutil

    # --- Part 1: real data (offseason = empty games, trivially passes) ---
    real_doc = generate(DATA)
    _validate_schema(real_doc)
    print(f"[demo] real run OK  games={len(real_doc['games'])}  slate={real_doc['slate_id']}")

    # --- Part 2: synthetic NFL board event to exercise join + edge_pts check ---
    # Build a minimal tmp data dir that mirrors real slates but adds a fake NFL event.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Copy real slate files
        shutil.copy(DATA / "slates.json", tmp_path / "slates.json")
        slates_meta = json.loads((DATA / "slates.json").read_text())
        slate_id = slates_meta["latest"]
        shutil.copy(DATA / f"{slate_id}.json", tmp_path / f"{slate_id}.json")

        # Read one real game from the slate for its (home, away, pick, prob)
        slate_games = json.loads((tmp_path / f"{slate_id}.json").read_text())["games"]
        sg = slate_games[0]  # e.g. NE @ SEA, pick=SEA
        home_abbr = sg["home"]   # "SEA"
        away_abbr = sg["away"]   # "NE"
        ind = sg["independent"]
        pick = ind["pick"]       # "SEA"

        # Reverse-map abbrev -> full name for board side names
        rev_map = {v: k for k, v in TEAM_MAP.items()}
        home_full = rev_map.get(home_abbr, home_abbr)
        away_full = rev_map.get(away_abbr, away_abbr)
        pick_full = rev_map.get(pick, pick)

        best_p, worst_p = -190, -235  # two real quotes

        fake_event = {
            "id": "fake001",
            "home": home_full,
            "away": away_full,
            "starts": sg["kickoff"],
            "sides": [
                {
                    "name": pick_full,
                    "quotes": [{"book": "BookA", "price": best_p},
                               {"book": "BookB", "price": worst_p}],
                    "best_price": best_p,
                    "best_book": "BookA",
                    "worst_price": worst_p,
                    "worst_book": "BookB",
                    "n_books": 2,
                    "gain_pts": round(
                        (american_to_prob(worst_p) - american_to_prob(best_p)) * 100, 2),
                }
            ],
            "max_gain_pts": 0,
            "n_books": 2,
        }

        fake_board = {
            "generated_at": "2026-08-11T00:00:00+00:00",
            "window_hours": 36,
            "credits_spent": 0,
            "sports_live": ["NFL"],
            "note": "",
            "boards": [{
                "sport": "nfl",
                "label": "NFL",
                "n_events": 1,
                "avg_gain_pts": 0,
                "max_gain_pts": 0,
                "n_books": 2,
                "events": [fake_event],
            }],
            "totals": {"events": 1, "avg_gain_pts": 0, "max_gain_pts": 0},
        }
        (tmp_path / "board.json").write_text(json.dumps(fake_board))

        synth_doc = generate(tmp_path)

    _validate_schema(synth_doc)
    assert len(synth_doc["games"]) >= 1, "synthetic join produced no games"

    g = synth_doc["games"][0]
    assert g["pick"] == pick, f"pick mismatch: {g['pick']} != {pick}"

    # edge_pts check: (worst_implied - best_implied) * 100
    expected_edge = round(
        (american_to_prob(worst_p) - american_to_prob(best_p)) * 100, 2)
    assert abs(g["edge_pts"] - expected_edge) < 0.1, (
        f"edge_pts {g['edge_pts']} != expected {expected_edge}")

    print(f"[demo] synthetic join OK  pick={g['pick']}  edge_pts={g['edge_pts']}  "
          f"expected={expected_edge}")
    print("[demo] all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="run self-check")
    ap.add_argument("--out", default=str(DATA))
    a = ap.parse_args()

    if a.demo:
        demo()
        return

    doc = generate(Path(a.out))
    print(f"generated_at : {doc['generated_at']}")
    print(f"slate_id     : {doc['slate_id']}")
    print(f"games        : {len(doc['games'])}")
    print(f"avg_edge_pts : {doc['avg_edge_pts']}")
    print(f"max_edge_pts : {doc['max_edge_pts']}")
    print(f"n_books      : {doc['n_books']}")


if __name__ == "__main__":
    main()
