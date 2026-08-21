"""Print "SEASON WEEK" for the next sealable NFL slate, or nothing.

The next sealable slate is the earliest (season, week) that still has an
unplayed game with a future kickoff. Printing nothing (exit 0) means there is
nothing to seal — the offseason, or a fully-played schedule — and seal.yml
treats empty output as a clean no-op, not an error.

    python scripts/next_slate_week.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.adapters.nfl import NFLAdapter


def main() -> None:
    adapter = NFLAdapter(cache_dir=Path("data/raw"))
    adapter.fetch(force=True)
    df = adapter.games
    now = datetime.now(timezone.utc)

    upcoming = df[df["home_score"].isna()].copy()
    if upcoming.empty:
        return
    upcoming["week_n"] = pd.to_numeric(upcoming["week"], errors="coerce")
    upcoming = upcoming.dropna(subset=["week_n"])

    for (season, week), grp in sorted(
            upcoming.groupby(["season", "week_n"]).groups.items()):
        rows = upcoming.loc[grp]
        kicks = [adapter._kickoff(r) for _, r in rows.iterrows()]
        if any(k > now for k in kicks):
            print(f"{int(season)} {int(week)}")
            return


if __name__ == "__main__":
    main()
