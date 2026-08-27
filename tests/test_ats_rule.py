"""The spread decision rule, whose sign conventions are the easy thing to
invert and the expensive thing to get wrong.

``spread_line`` is on the home basis and positive when the home side lays
points — verified against 7,276 completed games, where the home side wins
73.3% when spread_line > 3 and 28.4% when spread_line < -3. Every assertion
below hangs off that.
"""
import numpy as np
import pandas as pd

from engine.models.ensemble import (EDGE_THRESHOLD, ats_frame, selectivity,
                                    wilson)


def _f(rows):
    """rows: (pred_margin, spread_line, actual_margin)"""
    return pd.DataFrame(
        [{"m": m, "spread_line": s, "margin": a, "season": 2020}
         for m, s, a in rows])


def test_edge_sign_picks_the_side_we_actually_prefer():
    # home favoured by 3, we make them 10 better -> we like the home side by 7
    d = ats_frame(_f([(10.0, 3.0, 0.0)]), "m")
    assert d["edge"].iloc[0] == 7.0
    assert bool(d["pick_home"].iloc[0]) is True
    # home favoured by 10, we make them only 3 better -> we like the AWAY side
    d = ats_frame(_f([(3.0, 10.0, 0.0)]), "m")
    assert d["edge"].iloc[0] == -7.0
    assert bool(d["pick_home"].iloc[0]) is False


def test_underdog_flag_follows_the_side_taken_not_the_home_team():
    # home laying 7, we take home -> we are on the favourite
    assert not ats_frame(_f([(14.0, 7.0, 0.0)]), "m")["underdog"].iloc[0]
    # home laying 7, we take away -> we are on the dog
    assert ats_frame(_f([(0.0, 7.0, 0.0)]), "m")["underdog"].iloc[0]
    # home getting 7, we take home -> we are on the dog
    assert ats_frame(_f([(0.0, -7.0, 0.0)]), "m")["underdog"].iloc[0]
    # home getting 7, we take away -> we are on the favourite
    assert not ats_frame(_f([(-14.0, -7.0, 0.0)]), "m")["underdog"].iloc[0]


def test_grading_a_cover_a_loss_and_a_push():
    d = ats_frame(_f([
        (10.0, 3.0, 7.0),    # took home -3, home won by 7  -> cover
        (10.0, 3.0, 1.0),    # took home -3, home won by 1  -> loss
        (10.0, 3.0, 3.0),    # took home -3, home won by 3  -> push
        (-10.0, 3.0, 1.0),   # took away +3, home won by 1  -> cover
    ]), "m")
    assert list(d["win"]) == [True, False, False, True]
    assert list(d["push"]) == [False, False, True, False]


def test_threshold_is_absolute_and_may_select_nothing():
    """The point of the change: a slate where the model agrees with the market
    everywhere produces no plays at all, rather than promoting its least-bad
    disagreement the way a within-week rank does."""
    quiet = _f([(m, m - 0.5, 0.0) for m in (1.0, 2.0, 3.0)])
    d = ats_frame(quiet, "m")
    assert (d["edge"].abs() >= EDGE_THRESHOLD).sum() == 0
    assert selectivity(quiet, "m")["live"]["n"] == 0


def test_selectivity_narrows_the_sample_as_the_bar_rises():
    rng = np.random.default_rng(0)
    n = 400
    frame = pd.DataFrame({
        "m": rng.normal(0, 8, n),
        "spread_line": rng.normal(0, 6, n),
        "margin": rng.normal(0, 13, n),
        "season": rng.integers(2016, 2026, n),
    })
    rows = selectivity(frame, "m")["thresholds"]
    counts = [r["all"]["n"] for r in rows]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == n
    # dog and favourite partition the selected games, no game in both
    for r in rows:
        assert r["underdog"]["n"] + r["favourite"]["n"] == r["all"]["n"]


def test_wilson_widens_on_small_samples_and_brackets_the_rate():
    lo_s, hi_s = wilson(55, 100)
    lo_l, hi_l = wilson(550, 1000)
    assert lo_s < 0.55 < hi_s and lo_l < 0.55 < hi_l
    assert (hi_s - lo_s) > (hi_l - lo_l)
    assert np.isnan(wilson(0, 0)[0])
