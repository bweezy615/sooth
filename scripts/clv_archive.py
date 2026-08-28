"""Rebuild the NFL closing-line archive the /tools CLV checker compares against.

    python scripts/clv_archive.py

Why this exists
---------------
``site/public/data/clv-nfl.json`` was committed once, on 2026-08-06, by hand.
For twenty-two days a visitor could type a price into /tools and be told, to two
decimal places, whether they beat the close - against a 104 KB payload that
nothing in this repository could rebuild or check. On a site whose argument is
that its numbers are reproducible, a published artifact with no generator is the
same defect as a hand-typed figure, just larger.

It turned out to be correct. Regenerating it from ``data/backfill/`` reproduces
all 855 games, every closing price, every de-vigged fair probability and every
date exactly. That is a good outcome and it was luck: nobody could have known.
Now the reproduction is a test (``tests/test_clv_archive.py``), so the archive
and the evidence it claims to summarise cannot drift apart in silence, and a
newly backfilled season that never made it into the published file turns the
gate red.

Method, and the one place it matters
------------------------------------
Consensus is the **median of the implied probabilities** across books, then
converted back to American odds - never the median of the American prices
themselves. American odds are discontinuous across +/-100: the median of
[-104, +100] taken numerically is -2, which is not a price. Sixteen of these 855
games sit close enough to even money for that to matter.

Each game also carries ``nb``, the number of books in its consensus. /tools used
to describe the archive as "the consensus close across 10-16 books"; the real
range on moneylines is 7 to 16, median 11. The page now reads the count off the
game the visitor selected instead of quoting a remembered range.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from engine.closing import load_backfill
from engine.schema import american_to_prob, devig, prob_to_american

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/public/data/clv-nfl.json"


def build(pattern: str = "data/backfill/nfl_*.jsonl") -> dict[str, Any]:
    df = load_backfill(pattern)
    ml = df[df["market"] == "moneyline"]

    games: list[dict[str, Any]] = []
    for _, g in ml.groupby("event_id", sort=False):
        home = g[g["selection"] == "side_a"]["price"]
        away = g[g["selection"] == "side_b"]["price"]
        if home.empty or away.empty:
            continue
        # Median the PROBABILITIES. See the module docstring.
        ph = float(np.median([american_to_prob(int(p)) for p in home]))
        pa = float(np.median([american_to_prob(int(p)) for p in away]))
        fh, fa = devig(ph, pa)
        games.append({
            "s": int(g["season"].iloc[0]),
            "w": int(g["week"].iloc[0]),
            "h": str(g["home"].iloc[0]),
            "a": str(g["away"].iloc[0]),
            "t": str(g["commence_time"].iloc[0])[:10],
            "ch": prob_to_american(ph),
            "ca": prob_to_american(pa),
            "fh": round(fh, 4),
            "fa": round(fa, 4),
            # How many books stood behind this consensus. Published so the page
            # can state it per game rather than quoting a range from memory.
            "nb": int(g["book"].nunique()),
        })

    games.sort(key=lambda x: (x["s"], x["w"], x["t"], x["h"]))
    books = [x["nb"] for x in games]
    lo, hi = (min(books), max(books)) if books else (0, 0)
    seasons = sorted({g["s"] for g in games})
    # The note is built from the data it describes. The committed one said
    # "across 10-16 books" and the real moneyline range is 7-16.
    note = (f"NFL moneyline consensus closes {seasons[0]}-{str(seasons[-1])[2:]}: "
            f"median close price per side across {lo}-{hi} books, and de-vigged "
            f"fair probabilities.") if games else ""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "python scripts/clv_archive.py",
        "note": note,
        "n_games": len(games),
        "books_min": lo,
        "books_max": hi,
        "games": games,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="data/backfill/nfl_*.jsonl")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    res = build(a.pattern)
    seasons = sorted({g["s"] for g in res["games"]})
    print(f"games   : {res['n_games']} across seasons {seasons}")
    print(f"books   : {res['books_min']}-{res['books_max']} per game")
    tmp = Path(str(a.out) + ".tmp")
    tmp.write_text(json.dumps(res, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(tmp, a.out)
    print(f"written : {a.out}")


if __name__ == "__main__":
    main()
