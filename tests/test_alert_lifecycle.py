"""A week nobody has played must never be announced as a result.

2026-W01-nfl was sealed on 2026-09-01 with its first kickoff eight days out. It
entered site/public/data/pickengine-record.json immediately, carrying
n_settled 0, and engine/alert_lifecycle.graded_content had no guard against
that: it happily returned a "games settled: 0" announcement for a week that had
not happened. Worse, the watermark is saved on BOTH the zero-recipient path and
the successful-send path, so the key graded:2026-W01-nfl was burned and the real
results email could never send - the run would just print "already announced".

engine/alert_lifecycle._selfcheck() carries the same logic assertions, but
nothing runs it: it appears only in docs/alerts-runbook.md, and on Windows it
cannot run at all, because seal_content formats dates with the glibc-only %-d
that MSVC's strftime rejects. So the check lives here too, where
scripts/check.sh runs it on every platform.

The second test is the one that would have caught the actual damage. The first
only proves the logic; this one reads the real watermark against the real record.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.alert_lifecycle import graded_content, load_sent

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "site/public/data/pickengine-record.json"
WATERMARK = ROOT / "data/lifecycle_sent.json"


def test_a_sealed_but_unplayed_week_is_never_announced():
    """No settled games means no result, however the count is missing."""
    for week in ({"slate_id": "2026-W01-nfl", "n_settled": 0, "by_model": {}},
                 {"slate_id": "2026-W01-nfl", "n_settled": None},
                 {"slate_id": "2026-W01-nfl"}):
        assert graded_content({"weeks": [week]}) is None, week

    # ...and a week that HAS been played still announces, losses included.
    played = {"slate_id": "2026-W01-nfl", "n_settled": 16,
              "by_model": {"elo+epa-v1": {"record": "6-10"}}}
    got = graded_content({"weeks": [played]})
    assert got is not None and got[0] == "graded:2026-W01-nfl"
    assert "6-10" in got[1]


def test_no_graded_watermark_for_a_week_the_record_calls_unplayed():
    """The published data, not a fixture. This is the state that broke.

    If this fails, a results email has been marked sent for a week the site
    says nobody played - so the genuine one can never go out.
    """
    weeks = {str(w.get("slate_id")): w for w in
             json.loads(RECORD.read_text(encoding="utf-8")).get("weeks", [])}
    for key in sorted(load_sent(str(WATERMARK))):
        kind, _, slate = key.partition(":")
        if kind != "graded" or slate not in weeks:
            continue
        n = weeks[slate].get("n_settled")
        assert isinstance(n, (int, float)) and n > 0, (
            f"{key} is watermarked as already announced, but the published "
            f"record says {slate} has n_settled={n!r}. The results email for "
            f"that week is now permanently suppressed.")
