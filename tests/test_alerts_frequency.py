"""The /alerts frequency claim must be a measurement, not a memory.

The page used to say, in hand-typed prose, "160 divergences between Aug 10 and
Aug 22 ... about 13 a day". Replayed through today's detector the same window
gives 114, about 8.8 a day: the evidence never moved (data/capture is
append-only) but the detector was fixed three times and the sentence could not
tell. It also quoted 2.0 points, which is not one of the thresholds the form
offers, and counted player props, which the sender has never been able to send.

These tests hold the replacement together: the figure is generated, the
generator agrees with the detector it claims to be replaying, and the page
carries no digits of its own.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from engine.alert_email import RESEND_STEP, alert_key
from engine.alerts import find_divergence
from scripts.alert_frequency import BANDS, replay

ROOT = Path(__file__).resolve().parents[1]
ALERTS_HTML = ROOT / "site/public/alerts.html"
FREQ_JSON = ROOT / "site/public/data/alert-frequency.json"


def _payload() -> dict:
    return json.loads(FREQ_JSON.read_text(encoding="utf-8"))


# --- the page may not remember a number -----------------------------------

def test_the_frequency_paragraph_carries_no_hand_typed_figures():
    """#freq is built from the feed at runtime. A digit in the markup is a
    figure nothing regenerates, which is exactly how the old one went stale."""
    html = ALERTS_HTML.read_text(encoding="utf-8")
    m = re.search(r'<p id="freq".*?</p>', html, re.S)
    assert m, "alerts.html no longer has the #freq paragraph - update this test"
    assert not re.search(r"\d", m.group(0)), (
        "a number has been hand-typed back into the /alerts frequency "
        "paragraph; it must come from /data/alert-frequency.json: "
        + m.group(0))


def test_the_band_descriptions_quote_no_rate_of_their_own():
    """Each band's measured rate is rendered into its .bm span from the feed."""
    html = ALERTS_HTML.read_text(encoding="utf-8")
    for body in re.findall(r'<span class="bd">(.*?)</span>', html, re.S):
        assert not re.search(r"\d+(\.\d+)?\s*(a day|/day|per day|emails)", body), (
            "a band description states a rate in the markup; the measured rate "
            "belongs in its .bm span, from the feed: " + body.strip()[:120])


def test_the_published_bands_are_the_bands_the_form_offers():
    """Quoting a frequency at a threshold nobody can select is what the old
    sentence did with 2.0 - the workflow's no-subscribers floor, never a
    choice on the form."""
    html = ALERTS_HTML.read_text(encoding="utf-8")
    offered = {float(v) for v in
               re.findall(r'<input type="radio" name="min" value="([\d.]+)"', html)}
    assert offered, "alerts.html no longer declares min-point radios"
    assert offered == set(BANDS), (
        f"the form offers {sorted(offered)} but scripts/alert_frequency.py "
        f"measures {sorted(BANDS)}")
    assert {float(k) for k in _payload()["bands"]} == offered, (
        "site/public/data/alert-frequency.json was generated for different "
        "bands than the form offers - rerun scripts/alert_frequency.py")


# --- the payload must add up ----------------------------------------------

def test_the_published_payload_is_internally_consistent():
    p = _payload()
    start = datetime.fromisoformat(p["window_start"]).date()
    end = datetime.fromisoformat(p["window_end"]).date()
    assert (end - start).days + 1 == p["days"], (
        f"window {p['window_start']}..{p['window_end']} is not {p['days']} days")
    for key, band in p["bands"].items():
        assert float(key) == band["min_pts"]
        assert sum(band["per_day"].values()) == band["alerts"], (
            f"band {key}: per_day sums to {sum(band['per_day'].values())} but "
            f"alerts says {band['alerts']}")
        assert sum(band["by_sport"].values()) == band["alerts"]
        assert band["per_day_mean"] == round(band["alerts"] / p["days"], 1)
        for day in band["per_day"]:
            assert p["window_start"] <= day <= p["window_end"], (
                f"band {key} counts an alert on {day}, outside its own window")


def test_a_higher_threshold_never_reports_more_alerts():
    """Monotonicity is the cheapest possible check that the replay is not
    double-counting: a 4-point bar cannot fire more often than a 1.5-point one."""
    p = _payload()
    counts = [p["bands"][f"{b:g}"]["alerts"] for b in sorted(BANDS)]
    assert counts == sorted(counts, reverse=True), (
        f"alert counts {counts} rise with the threshold {sorted(BANDS)}")


# --- the replay must be the detector, not an impression of it -------------

def _row(book: str, price: int, cycle: str, sel: str = "Home") -> dict:
    return {"event_id": "e1", "market": "moneyline", "selection": sel,
            "line": None, "book": book, "price": price, "sport": "mlb",
            "home": "Home", "away": "Away", "provenance": "own_capture",
            "kickoff": "2026-08-14T23:00:00Z", "observed_at": cycle}


CYCLES = ["2026-08-14T12:00:00+00:00", "2026-08-14T13:00:00+00:00",
          "2026-08-14T14:00:00+00:00"]


def _fixture() -> list[dict]:
    rows = []
    for i, cycle in enumerate(CYCLES):
        for book in ("DraftKings", "FanDuel", "BetMGM"):
            rows.append(_row(book, -110, cycle))
        # one book far off the pack, and it moves further out on the last cycle
        rows.append(_row("BetOnline", 150 if i == 2 else 120, cycle))
    return rows


def test_replay_counts_one_opportunity_once_and_a_growing_one_twice():
    res = replay(_fixture(), 1.5)
    assert res["alerts"] == 2, (
        "a book sitting out of line across three cycles is one alert; growing "
        f"from +120 to +150 is a second. got {res}")
    assert res["per_day"] == {"2026-08-14": 2}
    assert res["by_sport"] == {"mlb": 2}


def test_replay_agrees_with_running_the_detector_over_the_whole_history():
    """The replay hands find_divergence a set already reduced to the latest row
    per (event, market, selection, line, book). That is only legitimate because
    the function's own first step is that same reduction. This asserts it, so
    the optimisation cannot quietly become a different measurement."""
    rows = _fixture()
    naive: dict[str, float] = {}
    events = 0
    for cycle in CYCLES:
        now = datetime.fromisoformat(cycle)
        upto = [r for r in rows if r["observed_at"] <= cycle]
        for alert in find_divergence(upto, 1.5, now=now):
            a = alert.to_dict()
            k, pts = alert_key(a), a["move_pts"]
            before = naive.get(k)
            if before is not None and pts < before + RESEND_STEP:
                continue
            naive[k] = max(pts, before or 0.0)
            events += 1
    assert events == replay(rows, 1.5)["alerts"]


def test_the_detector_can_be_asked_what_it_would_have_said_earlier():
    """Without an injectable `now` there is no way to reproduce a published
    frequency at all: both detectors read the newest price and drop started
    games, so they only ever answer about this instant."""
    rows = _fixture()
    after_kickoff = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    assert find_divergence(rows, 1.5, now=after_kickoff) == [], (
        "a game that has started must not produce an alert")
    before = datetime.fromisoformat(CYCLES[-1])
    assert find_divergence(rows, 1.5, now=before), (
        "the same rows, asked about a moment before kickoff, must fire")
