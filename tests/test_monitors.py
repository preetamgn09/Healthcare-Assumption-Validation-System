"""Analytic tests for monitors (BRIEF §38). Each has a known answer computed independently
of the implementation. Synthetic data is legitimate here and only here (BRIEF §47)."""
import numpy as np
import pandas as pd
import pytest

from havm.monitors.base import MonitorResult, benjamini_hochberg, normalise
from havm.monitors.distribution import linear_mmd, population_stability_index
from havm.monitors.structural import fairness_monitor


# ------------------------------------------------------------------ PSI
def test_psi_is_near_zero_for_identical_distributions():
    rng = np.random.default_rng(0)
    a = pd.Series(rng.normal(size=50_000))
    b = pd.Series(rng.normal(size=50_000))
    assert population_stability_index(a, b, 10, categorical=False) < 0.01


def test_psi_detects_a_mean_shift():
    rng = np.random.default_rng(1)
    a = pd.Series(rng.normal(0, 1, 50_000))
    b = pd.Series(rng.normal(1.5, 1, 50_000))
    assert population_stability_index(a, b, 10, categorical=False) > 0.20


def test_psi_is_zero_for_identical_categoricals():
    a = pd.Series(["x"] * 600 + ["y"] * 400)
    assert population_stability_index(a, a.copy(), 10, categorical=True) == pytest.approx(0.0, abs=1e-9)


def test_psi_reacts_to_a_categorical_reweighting():
    a = pd.Series(["x"] * 900 + ["y"] * 100)
    b = pd.Series(["x"] * 400 + ["y"] * 600)
    assert population_stability_index(a, b, 10, categorical=True) > 0.20


def test_psi_is_non_negative():
    rng = np.random.default_rng(2)
    for _ in range(20):
        a = pd.Series(rng.normal(size=2_000))
        b = pd.Series(rng.normal(rng.uniform(-2, 2), 1, 2_000))
        assert population_stability_index(a, b, 10, categorical=False) >= 0.0


# ------------------------------------------------------------------ MMD
def test_mmd_is_near_zero_when_p_equals_q():
    rng = np.random.default_rng(3)
    X, Y = rng.normal(size=(20_000, 5)), rng.normal(size=(20_000, 5))
    assert abs(linear_mmd(X, Y, seed=0, max_samples=20_000)["mmd2"]) < 0.01


def test_mmd_grows_with_separation():
    rng = np.random.default_rng(4)
    X = rng.normal(size=(20_000, 5))
    near = linear_mmd(X, rng.normal(0.2, 1, (20_000, 5)), seed=0, max_samples=20_000)["mmd2"]
    far = linear_mmd(X, rng.normal(2.0, 1, (20_000, 5)), seed=0, max_samples=20_000)["mmd2"]
    assert far > near > 0


# ------------------------------------------------------------------ FDR
def test_bh_rejects_nothing_when_all_null():
    assert not any(benjamini_hochberg([1.0] * 50, 0.05))


def test_bh_rejects_a_clear_signal():
    p = [1e-12] + [0.9] * 49
    rejected = benjamini_hochberg(p, 0.05)
    assert rejected[0] and sum(rejected) == 1


def test_bh_controls_false_positives_under_the_global_null():
    """Uncorrected, 500 uniform p-values give ~25 rejections at alpha=0.05.
    BH should give approximately none — which is the whole point of applying it."""
    rng = np.random.default_rng(5)
    p = list(rng.uniform(size=500))
    uncorrected = sum(x <= 0.05 for x in p)
    assert uncorrected > 10
    assert sum(benjamini_hochberg(p, 0.05)) <= 2


def test_bh_is_at_least_as_conservative_as_uncorrected():
    rng = np.random.default_rng(6)
    p = list(rng.uniform(size=200))
    assert sum(benjamini_hochberg(p, 0.05)) <= sum(x <= 0.05 for x in p)


# ------------------------------------------------------------------ normalisation
def test_normalisation_saturates_at_the_threshold():
    assert normalise(0.10, 0.20) == pytest.approx(0.5)
    assert normalise(0.20, 0.20) == pytest.approx(1.0)
    assert normalise(9.99, 0.20) == 1.0          # saturation: severity beyond the bound is invisible
    assert normalise(0.0, 0.20) == 0.0
    assert normalise(None, 0.20) == 0.0


def test_violation_outside_unit_interval_is_rejected():
    with pytest.raises(ValueError):
        MonitorResult(monitor="x", assumption="A1", evidence_class="OBSERVED",
                      raw={}, threshold={}, violation=1.5, triggered=True)


# ------------------------------------------------------------------ fairness
def _fairness_registry():
    return {
        "label_definition": {"name": "y"},
        "subgroups": {"attributes": ["g"], "min_group_size": 50},
        "monitor_config": {
            "normalisation": {"method": "threshold_relative"},
            "monitors": {"fairness": {
                "delta_tpr_threshold": 0.05, "delta_fpr_threshold": 0.05,
                "operating_point_quantile": 0.90, "min_positives": 30,
                "null_band": {"enabled": False},
            }},
        },
    }


def test_fairness_reports_no_disparity_when_groups_are_exchangeable():
    rng = np.random.default_rng(7)
    n = 20_000
    probs = rng.uniform(size=n)
    df = pd.DataFrame({
        "g": rng.choice(["a", "b"], n),      # group assigned independently of everything
        "y": rng.binomial(1, 0.3, n),
    })
    r = fairness_monitor(df, probs, _fairness_registry())
    assert r.raw["max_delta_tpr"] < 0.05 and not r.triggered


def test_fairness_detects_an_injected_disparity():
    rng = np.random.default_rng(8)
    n = 20_000
    g = rng.choice(["a", "b"], n)
    y = rng.binomial(1, 0.3, n)
    # Group "a" positives are scored high, group "b" positives low: a large, deliberate TPR gap.
    probs = np.where((g == "a") & (y == 1), 0.95, np.where(y == 1, 0.05, 0.5))
    r = fairness_monitor(pd.DataFrame({"g": g, "y": y}), probs, _fairness_registry())
    assert r.raw["max_delta_tpr"] > 0.5 and r.triggered and r.violation == 1.0


def test_fairness_suppresses_groups_with_too_few_positives():
    rng = np.random.default_rng(9)
    n = 5_000
    g = np.array(["a"] * (n - 120) + ["b"] * 120)      # b passes min_group_size, not min_positives
    y = np.where(g == "b", rng.binomial(1, 0.05, n), rng.binomial(1, 0.3, n))
    r = fairness_monitor(pd.DataFrame({"g": g, "y": y}), rng.uniform(size=n), _fairness_registry())
    suppressed = [s["group"] for s in r.evidence["suppressed"].get("g", [])]
    assert "b" in suppressed
