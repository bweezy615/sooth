# PLAN — NFL kickoff timezone fix (2026-09-01)

## The bug
`engine/adapters/nfl.py::_kickoff()` stamps nflverse `gametime` with
`tzinfo=timezone.utc`. nflverse `gameday`/`gametime` are US/Eastern. Every NFL
kickoff Sooth derives from that adapter is therefore 4 hours early in EDT
(5 hours in EST).

Proof: 2026 W1 `2026_01_TB_CIN` has `gametime=13:00` ET. Sealed slate publishes
`2026-09-13T13:00:00+00:00` (8 AM Central) instead of `17:00Z` (noon Central).
`/market`, which reads the odds feed, shows the correct noon — the two pages
disagree, which is the visible symptom.

## Blast radius
`_kickoff` feeds `Event.start_time`, `Result.settled_at`, `Line.captured_at`,
and `Prediction.created_at` (weekly.py:286). `created_at` is inside the merkle
leaf, so the fix changes the slate root.

## Fix
1. Convert via `ZoneInfo("America/New_York")` -> UTC, the same idiom already
   proven correct in `engine/backfill.py::kickoff_slots` and
   `engine/capture.py::minutes_to_next_kickoff`.
2. Regression test asserting a summer AND a winter row land on the right UTC
   instant (catches a hardcoded -4 as well as the current no-op).
3. Gate: `bash scripts/check.sh`.

## Explicitly NOT doing
- No editing of published evidence. `data/ledger/*.commitment.v1..v3.json` and
  the deployed `2026-W01-nfl.*` payloads stay byte-identical. The next weekly
  run mints commitment **v4** with `supersedes` pointing at the v3 root — the
  versioning path this system was built for. Silently rewriting v3 would look
  exactly like the tampering the merkle tree exists to disprove.
- Not touching `engine/adapters/epl.py` (date-only source, different question).
