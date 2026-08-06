"""Property-style tests for the Elo model, calibration, and ensemble helpers.

Everything here is pure math on synthetic data: deterministic, offline, no
network, no fixtures on disk.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from engine.calibrate import (
    Calibrator,
    expected_calibration_error,
    reliability,
    walk_forward_calibrate,
)
from engine.models.elo import EloConfig, EloModel
from engine.models.ensemble import _ats, _logit


# ---------------------------------------------------------------------------
# EloModel
# ---------------------------------------------------------------------------


def test_equal_ratings_neutral_is_even_money():
    m = EloModel()
    assert m.expected("A", "B", neutral=True) == pytest.approx(0.5)


def test_home_advantage_tilts_toward_home():
    m = EloModel()
    p_home = m.expected("A", "B")  # non-neutral
    assert p_home > 0.5
    # Symmetric: swapping venues mirrors the probability.
    assert m.expected("B", "A") == pytest.approx(p_home)


def test_expected_matches_logistic_form():
    m = EloModel()
    m.ratings = {"A": 1600.0, "B": 1500.0}
    diff = 100.0 + m.config.home_advantage
    want = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    assert m.expected("A", "B") == pytest.approx(want)


def test_expected_monotone_in_rating_gap():
    m = EloModel()
    probs = []
    for r in (1400.0, 1500.0, 1600.0, 1700.0):
        m.ratings = {"A": r, "B": 1500.0}
        probs.append(m.expected("A", "B", neutral=True))
    assert probs == sorted(probs)
    assert all(0.0 < p < 1.0 for p in probs)


def test_rest_advantage_helps_and_nan_rest_is_ignored():
    m = EloModel()
    base = m.expected("A", "B", neutral=True)
    rested = m.expected("A", "B", neutral=True, rest_diff=6.0)
    assert rested > base
    # Non-finite rest must not poison the probability.
    assert m.expected("A", "B", neutral=True, rest_diff=float("nan")) == (
        pytest.approx(base)
    )


def test_expected_margin_roundtrips_rating_diff():
    m = EloModel()
    for elo_diff in (-200.0, -50.0, 0.0, 75.0, 300.0):
        p = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
        margin = m.expected_margin(p)
        assert margin == pytest.approx(elo_diff / m.config.elo_per_point, abs=1e-9)


def test_expected_margin_clips_degenerate_probs():
    m = EloModel()
    assert math.isfinite(m.expected_margin(0.0))
    assert math.isfinite(m.expected_margin(1.0))
    assert m.expected_margin(1.0) > 0 > m.expected_margin(0.0)


def test_update_is_zero_sum_and_rewards_winner():
    m = EloModel()
    m.update("A", "B", margin=7.0, neutral=True)
    assert m.rating("A") > m.config.base_rating
    assert m.rating("B") < m.config.base_rating
    # Elo is conserved: what one side gains the other loses.
    assert m.rating("A") + m.rating("B") == pytest.approx(
        2 * m.config.base_rating
    )


def test_upset_moves_ratings_more_than_expected_win():
    fav_wins = EloModel()
    fav_wins.ratings = {"A": 1700.0, "B": 1400.0}
    fav_wins.update("A", "B", margin=7.0, neutral=True)
    expected_delta = fav_wins.rating("A") - 1700.0

    upset = EloModel()
    upset.ratings = {"A": 1700.0, "B": 1400.0}
    upset.update("B", "A", margin=7.0, neutral=True)  # underdog B wins at home-less
    upset_delta = upset.rating("B") - 1400.0

    assert expected_delta > 0
    assert upset_delta > expected_delta


def test_bigger_margin_bigger_update_with_damping():
    deltas = []
    for margin in (1.0, 7.0, 21.0):
        m = EloModel()
        m.update("A", "B", margin=margin, neutral=True)
        deltas.append(m.rating("A") - m.config.base_rating)
    assert deltas == sorted(deltas)
    # Log damping: tripling the margin far less than triples the delta.
    assert deltas[2] < 3 * deltas[1]


def test_tie_with_zero_margin_leaves_ratings_untouched():
    m = EloModel()
    m.ratings = {"A": 1550.0, "B": 1450.0}
    m.update("A", "B", margin=0.0, neutral=True)
    # log(|0| + 1) == 0 -> mov multiplier kills the update entirely.
    assert m.rating("A") == pytest.approx(1550.0)
    assert m.rating("B") == pytest.approx(1450.0)


def test_season_rollover_regresses_toward_mean():
    m = EloModel()
    m.ratings = {"A": 1700.0, "B": 1300.0}
    m.expected("A", "B", season=2024)  # establishes the season, no roll yet
    assert m.rating("A") == pytest.approx(1700.0)

    m.expected("A", "B", season=2025)  # new season triggers the roll
    c = m.config
    assert m.rating("A") == pytest.approx(
        c.base_rating + (1700.0 - c.base_rating) * c.season_carryover
    )
    assert m.rating("B") == pytest.approx(
        c.base_rating + (1300.0 - c.base_rating) * c.season_carryover
    )
    # Same season again: no double roll.
    m.expected("A", "B", season=2025)
    assert m.rating("A") == pytest.approx(1500.0 + 200.0 * c.season_carryover)


def test_walk_forward_convergence_toward_true_strength():
    """A always beats B; A's rating should climb monotonically in probability."""
    m = EloModel()
    p_first = m.expected("A", "B", neutral=True)
    for _ in range(20):
        m.update("A", "B", margin=10.0, neutral=True)
    p_last = m.expected("A", "B", neutral=True)
    assert p_first == pytest.approx(0.5)
    assert p_last > 0.75


# ---------------------------------------------------------------------------
# Calibrator / reliability / ECE
# ---------------------------------------------------------------------------


def test_unfitted_calibrator_is_identity():
    probs = np.array([0.1, 0.5, 0.9])
    out = Calibrator().transform(probs)
    assert np.array_equal(out, probs)


def test_fitted_calibrator_is_monotone_and_clipped():
    rng = np.random.default_rng(7)
    probs = rng.uniform(0.05, 0.95, size=800)
    # Truth generated from the probs themselves -> calibratable signal.
    outcomes = (rng.uniform(size=800) < probs).astype(float)
    cal = Calibrator().fit(probs, outcomes, through_season=2023)
    assert cal.fitted_through == 2023

    grid = np.linspace(0.0, 1.0, 101)
    mapped = cal.transform(grid)
    assert np.all(np.diff(mapped) >= -1e-12)  # isotonic => non-decreasing
    assert mapped.min() >= 0.01 - 1e-12
    assert mapped.max() <= 0.99 + 1e-12


def test_reliability_counts_partition_the_sample():
    rng = np.random.default_rng(11)
    probs = rng.uniform(size=500)
    outcomes = (rng.uniform(size=500) < 0.5).astype(float)
    tbl = reliability(probs, outcomes, bins=10)
    assert tbl["n"].sum() == 500
    # gap column is definitionally predicted - actual.
    assert np.allclose(tbl["gap"], (tbl["predicted"] - tbl["actual"]).round(4),
                       atol=1e-3)


def test_ece_zero_for_perfectly_calibrated_bucket():
    # 70% claims, exactly 70% hits -> zero calibration error.
    probs = np.full(100, 0.7)
    outcomes = np.array([1.0] * 70 + [0.0] * 30)
    assert expected_calibration_error(probs, outcomes) == pytest.approx(
        0.0, abs=1e-9
    )


def test_ece_detects_overconfidence():
    probs = np.full(100, 0.9)
    outcomes = np.array([1.0] * 50 + [0.0] * 50)  # actually a coin flip
    assert expected_calibration_error(probs, outcomes) == pytest.approx(
        0.4, abs=1e-3
    )


def test_ece_empty_input_is_nan():
    assert math.isnan(
        expected_calibration_error(np.array([]), np.array([]))
    )


def test_walk_forward_calibrate_passes_through_thin_history():
    frame = pd.DataFrame(
        {
            "season": [2020] * 100 + [2021] * 100,
            "p_home": np.linspace(0.2, 0.8, 200),
            "home_won": ([0, 1] * 100),
        }
    )
    out = walk_forward_calibrate(frame)
    # Fewer than 500 prior rows everywhere -> uncalibrated pass-through.
    assert np.allclose(out["p_home_cal"], out["p_home"])


def test_walk_forward_calibrate_never_uses_future_seasons():
    rng = np.random.default_rng(3)
    n1, n2 = 600, 100
    p1 = rng.uniform(0.05, 0.95, n1)
    p2 = rng.uniform(0.05, 0.95, n2)
    frame = pd.DataFrame(
        {
            "season": [2020] * n1 + [2021] * n2,
            "p_home": np.concatenate([p1, p2]),
            "home_won": np.concatenate(
                [
                    (rng.uniform(size=n1) < p1).astype(float),
                    (rng.uniform(size=n2) < p2).astype(float),
                ]
            ),
        }
    )
    out = walk_forward_calibrate(frame)
    s2020 = out[out["season"] == 2020]
    s2021 = out[out["season"] == 2021]
    # First season has no prior history: must be pass-through.
    assert np.allclose(s2020["p_home_cal"], s2020["p_home"])
    # Second season is calibrated on 2020 only, matching a manual refit.
    cal = Calibrator().fit(
        p1,
        frame.loc[frame["season"] == 2020, "home_won"].to_numpy(float),
        through_season=2020,
    )
    assert np.allclose(
        s2021["p_home_cal"].to_numpy(float),
        cal.transform(s2021["p_home"].to_numpy(float)),
    )


# ---------------------------------------------------------------------------
# Ensemble helpers (pure functions only - no data downloads)
# ---------------------------------------------------------------------------


def test_logit_inverts_sigmoid_and_clips():
    p = np.array([0.1, 0.25, 0.5, 0.75, 0.9])
    z = _logit(p)
    assert np.allclose(1.0 / (1.0 + np.exp(-z)), p)
    # Degenerate inputs are clipped, never infinite.
    assert np.all(np.isfinite(_logit(np.array([0.0, 1.0]))))


def test_ats_grades_picks_against_the_spread():
    # prob 0.75 -> implied margin = logit(0.75) * (400/ln10) / 25 ≈ 7.63 pts
    frame = pd.DataFrame(
        {
            "p": [0.75, 0.75, 0.75, 0.75],
            "spread_line": [3.0, 3.0, 20.0, 3.0],
            # actual home margins:
            "margin": [10.0, -3.0, 30.0, 3.0],
        }
    )
    # Row 0: pick home (7.63 > 3), cover 7 > 0 -> win
    # Row 1: pick home, cover -6 -> loss
    # Row 2: pick AWAY (7.63 < 20), cover 10 > 0 -> home covered -> loss
    # Row 3: cover exactly 0 -> push
    w, l, pu = _ats(frame, "p")
    assert (w, l, pu) == (1, 2, 1)
    assert w + l + pu == len(frame)


def test_ats_empty_frame_is_all_zero():
    frame = pd.DataFrame({"p": [np.nan], "spread_line": [np.nan],
                          "margin": [np.nan]})
    assert _ats(frame, "p") == (0, 0, 0)
