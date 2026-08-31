"""Analytic tests (BRIEF §38): metrics must behave correctly on examples whose answer
is known in advance. Synthetic data is legitimate here and ONLY here (BRIEF §47)."""
import numpy as np
import pytest

from havm.metrics import expected_calibration_error, rates_at_threshold


def test_perfect_calibration_gives_near_zero_ece():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.02, 0.98, 200_000)
    y = rng.binomial(1, p)          # outcomes generated from the stated probabilities
    ece = expected_calibration_error(y, p)["ece"]
    assert ece < 0.01, f"perfectly calibrated predictions should give ECE -> 0, got {ece}"


def test_miscalibration_is_detected():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.02, 0.98, 100_000)
    y = rng.binomial(1, p)
    overconfident = np.clip(p ** 2, 0, 1)   # systematically too low on the high end
    assert expected_calibration_error(y, overconfident)["ece"] > 0.05


def test_ece_is_bounded():
    y = np.array([0, 0, 1, 1])
    for probs in ([0.0, 0.0, 1.0, 1.0], [1.0, 1.0, 0.0, 0.0], [0.5] * 4):
        ece = expected_calibration_error(y, np.array(probs))["ece"]
        assert 0.0 <= ece <= 1.0


def test_ece_of_maximally_wrong_predictions_is_one():
    y = np.array([0, 0, 1, 1])
    assert expected_calibration_error(y, np.array([1.0, 1.0, 0.0, 0.0]))["ece"] == pytest.approx(1.0)


def test_rates_at_threshold_are_exact():
    y = np.array([1, 1, 0, 0])
    p = np.array([0.9, 0.4, 0.8, 0.1])
    r = rates_at_threshold(y, p, 0.5)
    assert r["tpr"] == pytest.approx(0.5)
    assert r["fpr"] == pytest.approx(0.5)
    assert r["precision"] == pytest.approx(0.5)
    assert r["n_flagged"] == 2
