"""Analytic tests for aggregation, triage, governance and audit (BRIEF §37–38)."""
import pytest

from havm.aggregation import compute_ahs
from havm.governance import AuditTrail, GovernanceEngine
from havm.triage import alert_packet, assess_harm


def _registry(weights=None, entry_mode=None, baselines=None, review=0.75, suspension=0.50,
              persistence=2, policy="renormalise"):
    return {
        "registry_version": "test",
        "registry_hash": "abc",
        "model": {"model_id": "m", "model_version": "1", "artifact": "x", "artifact_sha256": "y",
                  "features": {"numeric": [], "categorical": []}},
        "dataset": {"version": "d"},
        "freeze_baselines": baselines or {},
        "monitor_config": {
            "normalisation": {"method": "threshold_relative"},
            "ahs": {
                "weights": weights or {"a1_distribution": 0.5, "calibration": 0.3, "fairness": 0.2},
                "entry_mode": entry_mode or {},
                "missing_monitor_policy": policy,
            },
            "governance": {"bands": {"review": review, "suspension": suspension},
                           "persistence_windows": persistence, "require_corroboration": True,
                           "variants": ["separated", "collapsed"]},
        },
    }


def _result(name, violation, triggered=False, raw=None, threshold=None, assumption="A1"):
    return {"monitor": name, "assumption": assumption, "evidence_class": "OBSERVED",
            "raw": raw or {}, "threshold": threshold or {}, "violation": violation,
            "triggered": triggered, "evidence": {}, "notes": []}


# ------------------------------------------------------------------ AHS algebra
def test_ahs_is_one_when_nothing_is_violated():
    reg = _registry()
    r = compute_ahs([_result("a1_distribution", 0.0), _result("calibration", 0.0),
                     _result("fairness", 0.0)], reg)
    assert r["ahs"] == pytest.approx(1.0)


def test_ahs_is_zero_when_everything_is_maximally_violated():
    reg = _registry()
    r = compute_ahs([_result("a1_distribution", 1.0), _result("calibration", 1.0),
                     _result("fairness", 1.0)], reg)
    assert r["ahs"] == pytest.approx(0.0)


def test_ahs_decreases_when_one_violation_rises_and_others_are_fixed():
    reg = _registry()
    previous = 1.1
    for v in (0.0, 0.25, 0.5, 0.75, 1.0):
        ahs = compute_ahs([_result("a1_distribution", v), _result("calibration", 0.2),
                           _result("fairness", 0.1)], reg)["ahs"]
        assert ahs < previous
        previous = ahs


def test_ahs_stays_within_unit_interval():
    reg = _registry()
    for v in (0.0, 0.33, 0.99, 1.0):
        r = compute_ahs([_result("a1_distribution", v), _result("calibration", v),
                         _result("fairness", v)], reg)
        assert 0.0 <= r["ahs"] <= 1.0


def test_contributions_sum_to_the_deficit():
    reg = _registry()
    r = compute_ahs([_result("a1_distribution", 0.4), _result("calibration", 0.6),
                     _result("fairness", 0.2)], reg)
    total = sum(c["contribution_renormalised"] for c in r["components"].values())
    assert total == pytest.approx(r["deficit"])


# ------------------------------------------------------------------ H9 masking
def test_a_low_weight_monitor_cannot_trigger_review_alone():
    """H9: a monitor whose weight is below (1 - review band) cannot cross the band even at
    a total violation. Analytic, then confirmed numerically."""
    reg = _registry(weights={"a1_distribution": 0.9, "fairness": 0.1}, review=0.75)
    r = compute_ahs([_result("a1_distribution", 0.0), _result("fairness", 1.0)], reg)
    assert r["ahs"] > 0.75, "a total fairness violation should not reach the review band"
    assert "fairness" in r["masked_components"]


# ------------------------------------------------------------------ saturation
def test_saturation_makes_different_severities_indistinguishable():
    reg = _registry()
    a = compute_ahs([_result("a1_distribution", 1.0), _result("calibration", 1.0),
                     _result("fairness", 1.0)], reg)
    assert a["saturated_components"] == ["a1_distribution", "calibration", "fairness"]


# ------------------------------------------------------------------ missing monitors
def test_a_missing_monitor_makes_the_system_look_healthier():
    reg = _registry()
    full = compute_ahs([_result("a1_distribution", 1.0), _result("calibration", 1.0),
                        _result("fairness", 1.0)], reg)
    partial = compute_ahs([_result("a1_distribution", 1.0)], reg)
    assert partial["ahs_declared_weights"] > full["ahs"]
    assert partial["missing_monitors"] == ["calibration", "fairness"]
    assert partial["ahs_renormalised"] == pytest.approx(0.0)


# ------------------------------------------------------------------ baseline-relative entry
def test_baseline_relative_entry_is_zero_at_the_baseline():
    reg = _registry(entry_mode={"calibration": "baseline_relative"},
                    baselines={"calibration": {"metric_key": "ece", "threshold_key": "ece",
                                               "value": 0.006}})
    r = compute_ahs([_result("calibration", 0.12, raw={"ece": 0.006}, threshold={"ece": 0.05})], reg)
    assert r["components"]["calibration"]["violation_entering_ahs"] == pytest.approx(0.0)


def test_baseline_relative_entry_measures_change_not_level():
    reg = _registry(entry_mode={"calibration": "baseline_relative"},
                    baselines={"calibration": {"metric_key": "ece", "threshold_key": "ece",
                                               "value": 0.006}})
    r = compute_ahs([_result("calibration", 1.0, raw={"ece": 0.056}, threshold={"ece": 0.05})], reg)
    assert r["components"]["calibration"]["violation_entering_ahs"] == pytest.approx(1.0)


# ------------------------------------------------------------------ triage
def test_input_drift_alone_is_not_harm():
    reg = _registry()
    results = [_result("a1_distribution", 1.0, triggered=True),
               _result("calibration", 0.1, triggered=False, assumption="calibration"),
               _result("fairness", 0.1, triggered=False, assumption="fairness")]
    harm = assess_harm(results, compute_ahs(results, reg), reg)
    assert harm["harm_level"] == "NONE"        # uncorroborated single input detector


def test_two_input_detectors_give_potential_not_measured():
    reg = _registry(weights={"a1_distribution": 0.5, "a3_structural": 0.5})
    results = [_result("a1_distribution", 1.0, triggered=True),
               _result("a3_structural", 0.5, triggered=True, assumption="A3")]
    harm = assess_harm(results, compute_ahs(results, reg), reg)
    assert harm["harm_level"] == "POTENTIAL" and harm["corroborated"]


def test_behaviour_change_gives_measured_harm():
    reg = _registry()
    results = [_result("calibration", 1.0, triggered=True, assumption="calibration")]
    harm = assess_harm(results, compute_ahs(results, reg), reg)
    assert harm["harm_level"] == "MEASURED"


def test_disparity_inside_the_null_band_is_discounted():
    reg = _registry()
    results = [_result("fairness", 1.0, triggered=True, assumption="fairness",
                       raw={"exceeds_null_band": False, "worst_pair": None})]
    harm = assess_harm(results, compute_ahs(results, reg), reg)
    assert harm["harm_level"] == "NONE" and harm["discounted_as_noise"] == ["fairness"]


# ------------------------------------------------------------------ governance
def _harm(level, inputs=()):
    return {"harm_level": level, "input_monitors_triggered": list(inputs),
            "behaviour_monitors_triggered": [], "corroborated": True,
            "discounted_as_noise": [], "affected_population": None, "ahs": 0.9}


def test_escalation_requires_persistence():
    eng = GovernanceEngine(_registry(persistence=2), variant="separated")
    first = eng.step("w0", 0.4, _harm("MEASURED"))
    assert first["to_state"] == "NORMAL" and "held" in first["reason"]
    second = eng.step("w1", 0.4, _harm("MEASURED"))
    assert second["to_state"] == "ABSTENTION_RECOMMENDED"


def test_de_escalation_is_immediate():
    eng = GovernanceEngine(_registry(persistence=2), variant="separated")
    eng.step("w0", 0.4, _harm("MEASURED"))
    eng.step("w1", 0.4, _harm("MEASURED"))
    back = eng.step("w2", 0.95, _harm("NONE"))
    assert back["to_state"] == "NORMAL" and back["de_escalation"]


def test_separated_never_suspends_on_input_drift_alone():
    eng = GovernanceEngine(_registry(persistence=1), variant="separated")
    for i in range(5):
        eng.step(f"w{i}", 0.10, _harm("POTENTIAL", ["a1_distribution"]))
    assert not eng.summary()["reached_suspension"]


def test_collapsed_suspends_on_ahs_alone():
    eng = GovernanceEngine(_registry(persistence=1), variant="collapsed")
    for i in range(3):
        eng.step(f"w{i}", 0.10, None)
    assert eng.summary()["reached_suspension"]


# ------------------------------------------------------------------ audit
def test_audit_record_is_self_contained():
    reg = _registry()
    results = [_result("a1_distribution", 1.0, triggered=True,
                       raw={"max_psi": 3.3}, threshold={"psi": 0.2})]
    ahs = compute_ahs(results, reg)
    harm = assess_harm(results, ahs, reg)
    eng = GovernanceEngine(reg, variant="separated")
    gov = eng.step("w0", ahs["ahs"], harm)
    packet = alert_packet("w0", results, ahs, harm, gov, reg)

    audit = AuditTrail(reg)
    audit.record(window_id="w0", window_meta={"n": 10}, results=results, ahs_result=ahs,
                 harm=harm, governance={"separated": gov}, packet=packet)
    rec = audit.records[0]

    for field in ("timestamp", "model_version", "dataset_version", "registry_version",
                  "monitors", "ahs", "ahs_components", "harm_assessment", "governance",
                  "alert_packet", "rollback_information"):
        assert field in rec, f"audit record missing {field}"
    assert rec["monitors"][0]["raw"]["max_psi"] == 3.3
    assert rec["monitors"][0]["threshold"]["psi"] == 0.2
