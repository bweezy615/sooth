"""How much mail a price-alert subscriber actually gets, measured by replay.

/alerts tells a visitor how often we will email them. That sentence used to be
hand-typed - "160 divergences between Aug 10 and Aug 22, about 13 a day" - and
by 2026-08-28 it reproduced to 114, about 8.8 a day, because the detector had
since been fixed for three bugs that all inflated the count. The evidence never
moved; ``data/capture`` is append-only and every row from that window is still
on disk. Only the arithmetic over it changed, and nobody could tell, because the
sentence was a memory rather than a measurement.

So it is a measurement again:

    python scripts/alert_frequency.py

Method, and why it is not a second implementation of the detector
-----------------------------------------------------------------
Divergence detection is "as of now" by construction: ``find_divergence`` reads
the newest price each book has posted and drops games that have already
started. To ask what it would have said last Tuesday you have to hand it
Tuesday's ``now`` and Tuesday's prices, which is why ``engine.alerts`` now takes
an optional ``now``.

The replay walks the capture cycles in order, keeps the latest row per
(event, market, selection, line, book), and hands **that** to the real
``find_divergence``. Passing the reduced set is exactly equivalent to passing
the whole history, because the function's own first step is that same
reduction - verified against a naive full-history replay on 2026-08-10..11:
identical keys, identical magnitudes, 3x faster. Rows for games that have
started are dropped as we pass them, which is safe because a game cannot
un-start.

Dedup is the sender's, not an approximation of it: ``alert_email.alert_key``
plus ``RESEND_STEP``, so a book sitting out of line for six hours counts once
and a divergence that grows by a point counts again - which is what actually
lands in an inbox.

Population is the sender's too. ``alert_email.main`` calls
``alerts.scan(pattern, min_move=floor)`` and ``scan``'s ``include_props``
defaults to False, so player props have never been eligible for an alert email
and are not counted here. Sports are whatever the board currently fetches,
which is what ``load_observations`` defaults to.

Output: site/public/data/alert-frequency.json, rendered by /alerts at runtime.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine.alerts import find_divergence, load_observations, not_started
from engine.alert_email import RESEND_STEP, alert_key

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/public/data/alert-frequency.json"

# The thresholds /alerts actually offers. tests/test_alerts_frequency.py holds
# these against the radio buttons in the page, so the two cannot drift: quoting
# a frequency at a band nobody can select is how the old sentence ended up
# reporting 2.0 points, which was the workflow's no-subscribers floor and never
# a choice on the form.
BANDS = (1.5, 2.5, 4.0)

DEFAULT_DAYS = 14


def _ts(row: dict) -> str:
    return str(row.get("observed_at", ""))


def replay(rows: list[dict], min_move: float) -> dict[str, Any]:
    """Divergence alerts a subscriber at ``min_move`` would have been sent.

    ``rows`` is already restricted to the window. Returns the count, the
    per-day breakdown and which sports produced them.
    """
    by_cycle: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_cycle[_ts(r)].append(r)

    latest: dict[tuple, dict] = {}
    sent: dict[str, float] = {}
    per_day: collections.Counter = collections.Counter()
    by_sport: collections.Counter = collections.Counter()

    for cycle in sorted(by_cycle):
        try:
            now = datetime.fromisoformat(cycle.replace("Z", "+00:00"))
        except ValueError:
            continue
        for r in by_cycle[cycle]:
            key = (str(r.get("event_id")), str(r.get("market")),
                   str(r.get("selection")), str(r.get("line")),
                   str(r.get("book")))
            cur = latest.get(key)
            if cur is None or _ts(r) > _ts(cur):
                latest[key] = r
        latest = {k: v for k, v in latest.items() if not_started(v, now)}

        for alert in find_divergence(list(latest.values()), min_move, now=now):
            a = alert.to_dict()
            k = alert_key(a)
            pts = a["move_pts"]
            before = sent.get(k)
            if before is not None and pts < before + RESEND_STEP:
                continue
            sent[k] = max(pts, before or 0.0)
            per_day[cycle[:10]] += 1
            by_sport[str(a.get("sport", ""))] += 1

    return {
        "min_pts": min_move,
        "alerts": sum(per_day.values()),
        "per_day": dict(sorted(per_day.items())),
        "by_sport": dict(sorted(by_sport.items())),
    }


def measure(pattern: str = "data/capture/*/*.jsonl",
            days: int = DEFAULT_DAYS,
            bands: "tuple[float, ...]" = BANDS) -> dict[str, Any]:
    rows = load_observations(pattern)
    if not rows:
        raise SystemExit(f"no observations matched {pattern}")

    # The window ends on the last COMPLETE day. Ending it on the newest
    # observation would divide a part-day's alerts by a whole day and quietly
    # under-report the rate every time this runs before midnight UTC.
    newest = max(_ts(r) for r in rows)[:10]
    end = (datetime.fromisoformat(newest).date() - timedelta(days=1))
    start = end - timedelta(days=days - 1)
    lo, hi = start.isoformat(), end.isoformat()
    window = [r for r in rows if lo <= _ts(r)[:10] <= hi]

    out: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_start": lo,
        "window_end": hi,
        "days": days,
        "observations": len(window),
        "sports_watched": sorted({str(r.get("sport", "")) for r in window}),
        "markets": "game lines only - player props are not eligible for alerts",
        "bands": {},
    }
    for band in bands:
        res = replay(window, band)
        res["per_day_mean"] = round(res["alerts"] / days, 1)
        out["bands"][f"{band:g}"] = res
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="data/capture/*/*.jsonl")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    res = measure(a.pattern, a.days)
    print(f"window     : {res['window_start']} .. {res['window_end']} "
          f"({res['days']} days, {res['observations']} observations)")
    print(f"sports     : {', '.join(res['sports_watched'])}")
    for band, r in res["bands"].items():
        print(f"  {band:>4} pts : {r['alerts']:>4} alerts  "
              f"({r['per_day_mean']}/day)  {r['by_sport']}")

    tmp = Path(str(a.out) + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, a.out)
    print(f"written    : {a.out}")


if __name__ == "__main__":
    main()
