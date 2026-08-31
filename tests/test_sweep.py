"""Tests for the Gate 6 rescoring machinery. The sweep re-derives violations from cached
raw metrics, so a bug here would silently corrupt every sensitivity result."""
import numpy as np
import pytest

from havm.sweep import evaluate, raw_metric, rescore

WEIGHTS = {"a1_distribution": 0.5, "calibration": 0.3, "fairness": 0.2}


def _res(name, raw, threshold):
    return {"monitor": name, "assumption": name, "evidence_class": "OBSERVED",
            "raw": raw, "threshold": threshold, "violation": 0.0, "triggered": False}


def _bank(psi=0.0, ece=0.0, dtpr=0.0):
    return [
        _res("a1_distribution", {"max_psi": psi}, {"psi": 0.2}),
        _res("calibration", {"ece": ece}, {"ece": 0.05}),
        _res("fairness", {"max_delta_tpr": dtpr}, {"delta_tpr": 0.05}),
    ]


def _score(results, **kw):
    kw.setdefault("weights", WEIGHTS)
    kw.setdefault("normalisation", "threshold_relative")
    kw.setdefault("thresholds", {})
    kw.setdefault("baselines", {})
    kw.setdefault("entry_mode", {})
    kw.setdefault("ahs_band", 0.75)
    return rescore(results, **kw)


def test_raw_metric_reads_the_declared_key():
    assert raw_metric(_res("a1_distribution", {"max_psi": 3.3}, {"psi": 0.2})) == 3.3


def test_structural_raw_metric_is_the_affected_fraction():
    r = _res("a3_structural", {"n_columns_affected": 5, "n_columns_total": 25}, {})
    assert raw_metric(r) == pytest.approx(0.2)


def test_clean_window_scores_one():
    assert _score(_bank())["ahs"] == pytest.approx(1.0)


def test_ahs_falls_as_a_metric_rises():
    previous = 1.1
    for psi in (0.0, 0.05, 0.1, 0.2, 1.0):
        ahs = _score(_bank(psi=psi))["ahs"]
        assert ahs <= previous
        previous = ahs


def test_ablation_removes_the_monitor_entirely():
    s = _score(_bank(psi=1.0, ece=0.1), ablate={"a1_distribution"})
    assert "a1_distribution" not in s["components"]
    assert sum(c["weight"] for c in s["components"].values()) == pytest.approx(1.0)


def test_baseline_relative_subtracts_the_baseline():
    s = _score(_bank(ece=0.056), entry_mode={"calibration": "baseline_relative"},
               baselines={"calibration": 0.006})
    assert s["components"]["calibration"]["violation"] == pytest.approx(1.0)
    s0 = _score(_bank(ece=0.006), entry_mode={"calibration": "baseline_relative"},
                baselines={"calibration": 0.006})
    assert s0["components"]["calibration"]["violation"] == pytest.approx(0.0)


def test_empirical_quantile_places_the_metric_in_the_null_distribution():
    null = {m: np.array([0.001, 0.002, 0.003, 0.004])
            for m in ("a1_distribution", "calibration", "fairness")}
    below = _score(_bank(psi=0.0005), normalisation="empirical_quantile", null_quantiles=null)
    above = _score(_bank(psi=99.0), normalisation="empirical_quantile", null_quantiles=null)
    assert below["components"]["a1_distribution"]["violation"] == pytest.approx(0.0)
    assert above["components"]["a1_distribution"]["violation"] == pytest.approx(1.0)


def test_monotone_normalisations_preserve_ranking_below_saturation():
    """Key to reading EXP005b: below the bound both functions are monotone in the metric, so
    they order windows identically. Any difference in detection between them can only come
    from where the band sits, not from which windows are judged worse."""
    psis = [0.01, 0.05, 0.10, 0.15, 0.19]          # all below the 0.2 threshold
    single = {"a1_distribution": 1.0}
    a = [_score(_bank(psi=p), weights=single, normalisation="threshold_relative")["ahs"] for p in psis]
    b = [_score(_bank(psi=p), weights=single, normalisation="soft_exponential")["ahs"] for p in psis]
    assert np.argsort(a).tolist() == np.argsort(b).tolist()


def test_saturation_destroys_ranking_that_a_soft_normalisation_keeps():
    """Above the bound threshold_relative collapses every severity to the same value, so
    windows that differ by orders of magnitude become indistinguishable. This is the
    mechanism behind EXP003 Finding 3, isolated."""
    psis = [0.4, 2.0, 20.0]
    single = {"a1_distribution": 1.0}
    hard = [_score(_bank(psi=p), weights=single, normalisation="threshold_relative")["ahs"] for p in psis]
    soft = [_score(_bank(psi=p), weights=single, normalisation="soft_exponential")["ahs"] for p in psis]
    assert len(set(hard)) == 1, "threshold_relative should collapse all of these to one value"
    assert len(set(soft)) == 3 and soft[0] > soft[1] > soft[2]


def test_saturation_is_reported():
    s = _score(_bank(psi=5.0, ece=1.0, dtpr=1.0))
    assert set(s["saturated"]) == {"a1_distribution", "calibration", "fairness"}


def test_evaluate_matches_a_hand_computed_confusion_matrix():
    m = evaluate([True, True, False, False], [1, 0, 1, 0])
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == pytest.approx(0.5)
    assert m["recall"] == pytest.approx(0.5)
    assert m["false_alarm_rate"] == pytest.approx(0.5)


def test_evaluate_handles_no_alerts():
    m = evaluate([False, False], [1, 0])
    assert m["precision"] is None and m["recall"] == 0.0
