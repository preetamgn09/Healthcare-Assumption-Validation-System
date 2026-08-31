"""Analytic tests for the A2, A4 and OOD monitors."""
import numpy as np
import pandas as pd
import pytest

from havm.monitors.ood import TabularOOD, ood_monitor
from havm.monitors.relational import operational_monitor, relational_monitor, simulate_batch


def _registry(**over):
    monitors = {
        "a2_relational": {"psi_bins": 10, "score_psi_threshold": 0.20,
                          "auroc_delta_threshold": 0.05, "baseline_auroc": 0.70,
                          "label_delay_windows": 2},
        "a4_operational": {"delay_hours_threshold": 6.0, "latency_ms_threshold": 500.0,
                           "expected": {"schema_version": "v1", "pipeline_version": "1.0.0"}},
        "ood": {"reference_quantile": 0.99, "excess_rate_threshold": 0.05},
    }
    for k, v in over.items():
        monitors[k].update(v)
    return {"monitor_config": {"normalisation": {"method": "threshold_relative"},
                               "monitors": monitors}}


# ------------------------------------------------------------------ A2
def test_a2_is_silent_when_scores_and_discrimination_are_unchanged():
    rng = np.random.default_rng(0)
    ref = rng.beta(2, 8, 20_000)
    cur = rng.beta(2, 8, 20_000)
    y = rng.binomial(1, cur)
    r = relational_monitor(y, cur, ref, _registry(a2_relational={"baseline_auroc": None}))
    assert r.raw["score_psi"] < 0.05 and not r.triggered


def test_a2_detects_a_shift_in_the_score_distribution():
    rng = np.random.default_rng(1)
    ref = rng.beta(2, 8, 20_000)
    cur = rng.beta(6, 4, 20_000)
    r = relational_monitor(rng.binomial(1, cur), cur, ref,
                           _registry(a2_relational={"baseline_auroc": None}))
    assert r.raw["score_psi"] > 0.20 and r.triggered


def test_a2_detects_discrimination_loss():
    rng = np.random.default_rng(2)
    ref = rng.uniform(size=10_000)
    y = rng.binomial(1, 0.3, 10_000)
    r = relational_monitor(y, ref, ref, _registry())     # scores unrelated to y -> AUROC ~0.5
    assert r.raw["auroc_delta"] > 0.05 and r.triggered


def test_a2_label_blind_mode_reports_no_discrimination_signal():
    rng = np.random.default_rng(3)
    ref = rng.beta(2, 8, 5_000)
    r = relational_monitor(rng.binomial(1, 0.3, 5_000), ref, ref, _registry(),
                           labels_available=False)
    assert r.raw["auroc"] is None
    assert any("Labels withheld" in n for n in r.notes)


def test_a2_never_reports_a_negative_discrimination_delta():
    """An improvement over baseline is not a violation."""
    rng = np.random.default_rng(4)
    y = rng.binomial(1, 0.3, 10_000)
    probs = np.clip(y * 0.9 + rng.normal(0, 0.05, 10_000), 0.01, 0.99)   # near-perfect
    r = relational_monitor(y, probs, probs, _registry())
    assert r.raw["auroc_delta"] == 0.0


# ------------------------------------------------------------------ A4
def test_a4_is_silent_on_a_healthy_batch():
    r = operational_monitor(simulate_batch("w0", seed=0), _registry())
    assert not r.triggered and r.violation == 0.0


def test_a4_flags_a_missing_batch_at_full_violation():
    r = operational_monitor(simulate_batch("w0", seed=0, missing=True), _registry())
    assert r.triggered and r.violation == 1.0


def test_a4_flags_a_version_change():
    r = operational_monitor(simulate_batch("w0", seed=0, pipeline_version="2.0.0"), _registry())
    assert r.triggered and "pipeline_version_changed" in r.evidence["faults"]


def test_a4_scales_with_delay():
    small = operational_monitor(simulate_batch("w0", seed=0, delay_hours=6.0), _registry())
    large = operational_monitor(simulate_batch("w0", seed=0, delay_hours=60.0), _registry())
    assert small.violation <= large.violation and large.violation == 1.0


def test_a4_always_declares_itself_simulated():
    r = operational_monitor(simulate_batch("w0", seed=0), _registry())
    assert r.evidence_class == "SIMULATED"
    assert any("SIMULATED" in n for n in r.notes)


# ------------------------------------------------------------------ OOD
def _frame(n, seed, shift=0.0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "x1": rng.normal(shift, 1, n), "x2": rng.normal(shift, 1, n),
        "c1": rng.choice(["a", "b", "c"], n),
    })


def test_ood_detectors_score_shifted_data_higher():
    ref = _frame(4_000, 0)
    y = np.random.default_rng(0).binomial(1, 0.3, len(ref))
    det = TabularOOD(["x1", "x2"], ["c1"], max_reference=2_000).fit(ref, y)
    near = det.scores(_frame(2_000, 1, shift=0.0), np.full(2_000, 0.3))
    far = det.scores(_frame(2_000, 2, shift=4.0), np.full(2_000, 0.3))
    for name in ("mahalanobis", "knn", "isolation_forest"):
        assert far[name].mean() > near[name].mean(), f"{name} should score OOD data higher"


def test_entropy_and_max_softmax_are_monotone_equivalents_in_binary():
    """Not two independent detectors: for a binary model both are functions of |p - 0.5|,
    so identical AUROC in EXP007 is a correctness check, not a coincidence."""
    ref = _frame(500, 0)
    det = TabularOOD(["x1", "x2"], ["c1"], max_reference=400).fit(
        ref, np.random.default_rng(0).binomial(1, 0.3, len(ref)))
    from scipy.stats import spearmanr

    probs = np.linspace(0.01, 0.99, 200)
    s = det.scores(_frame(200, 5), probs)
    # Both are monotone increasing in min(p, 1-p), so they tie on p and 1-p. Rank
    # correlation is the right instrument; argsort would only compare tie-breaking order.
    # Not exactly 1.0: values that tie mathematically differ in the last floating-point
    # bits, so a handful of ranks swap. The tolerance covers that, not a real divergence.
    rho = spearmanr(s["predictive_entropy"], s["max_softmax"]).statistic
    assert rho == pytest.approx(1.0, abs=1e-4)


def test_ood_monitor_is_silent_when_the_flagged_rate_matches_the_reference():
    rng = np.random.default_rng(6)
    ref = rng.normal(size=10_000)
    r = ood_monitor(rng.normal(size=10_000), ref, _registry(), "test")
    assert r.raw["excess"] < 0.05 and not r.triggered


def test_ood_monitor_triggers_on_an_excess_flagged_rate():
    rng = np.random.default_rng(7)
    ref = rng.normal(size=10_000)
    r = ood_monitor(rng.normal(3.0, 1.0, 10_000), ref, _registry(), "test")
    assert r.raw["excess"] > 0.05 and r.triggered
