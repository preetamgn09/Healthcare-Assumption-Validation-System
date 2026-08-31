"""EXP003 — Gate 5: end-to-end replay.

    python scripts/run_g5.py

Two parts:

  A. OBSERVED  — the deployment domain partitioned into K windows at random. D2 has no
                 time axis, so this is NOT a trajectory. Its purpose is to test whether
                 AHS is stable across windows drawn from one distribution: a score that
                 wanders on a homogeneous stream would be measuring noise.

  B. INJECTED  — a declared severity ramp: clean windows, then increasing perturbation,
                 then recovery. Ordering is constructed and stated, not discovered. This
                 exercises escalation, persistence and de-escalation, and tests AHS
                 monotonicity in severity (H3).

Both governance variants (separated / collapsed) run on identical monitor output so their
escalation counts can be compared (H10/RQ9).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm import replay
from havm.aggregation import compute_ahs, explain
from havm.datasets.d2 import build_splits
from havm.governance import AuditTrail, GovernanceEngine
from havm.monitors.distribution import monitor as a1_monitor
from havm.monitors.structural import calibration_monitor, fairness_monitor, structural_monitor
from havm.triage import alert_packet, assess_harm
from havm.utils import environment_record, load_config, sha256_obj, write_json

EXPERIMENT_ID = "EXP003"


def run_monitors(window, reference, model, registry, features, label):
    probs = model.predict_proba(window[features])[:, 1]
    return [r.to_dict() for r in (
        a1_monitor(window, reference, registry),
        structural_monitor(window, registry),
        calibration_monitor(window[label].to_numpy(), probs, registry),
        fairness_monitor(window, probs, registry),
    )]


def freeze_baselines(validation, reference, model, registry, features, label) -> dict:
    """Measure each behaviour monitor on in-distribution validation data at freeze time.

    EXP002 finding (d): the frozen model already breaches the fairness bound
    in-distribution, so an absolute-threshold monitor contributes a constant violation from
    day one. Baseline-relative entry subtracts that constant, leaving only change.
    """
    results = {r["monitor"]: r for r in run_monitors(validation, reference, model, registry, features, label)}
    return {
        "calibration": {"metric_key": "ece", "threshold_key": "ece",
                        "value": results["calibration"]["raw"]["ece"]},
        "fairness": {"metric_key": "max_delta_tpr", "threshold_key": "delta_tpr",
                     "value": results["fairness"]["raw"]["max_delta_tpr"]},
    }


def perturb(df: pd.DataFrame, severity: float, seed: int, n_out: int) -> pd.DataFrame:
    """A declared perturbation of the data-generating process: progressively older and
    higher-utilisation case mix. Specified by its effect on the population, not by the
    statistic it is meant to move (scope.md §8.3 point 4).

    Window size is held constant at n_out by resampling. The first version of this ramp
    let the window shrink as severity rose (8,000 -> 4,957), which confounded severity with
    sample size: PSI and DeltaTPR are both noisier in smaller windows, so an apparent
    non-monotonicity could have been either. Holding n fixed leaves severity as the only
    variable."""
    rng = np.random.default_rng(seed)
    if severity <= 0:
        out = df.sample(n=n_out, replace=True, random_state=seed).copy()
    else:
        older = df["age"].isin(["[70-80)", "[80-90)", "[90-100)"])
        weights = np.where(older, 1.0, 1.0 - 0.7 * severity)
        out = df.sample(n=n_out, replace=True, weights=weights, random_state=seed).copy()
        out["number_inpatient"] = out["number_inpatient"] + int(round(3 * severity))
        out["number_emergency"] = out["number_emergency"] + int(round(2 * severity))
    return out


def process(windows, reference, model, registry, features, label, audit, engines, log):
    for window_id, frame, meta in windows:
        results = run_monitors(frame, reference, model, registry, features, label)
        ahs_result = compute_ahs(results, registry)
        harm = assess_harm(results, ahs_result, registry)

        decisions = {}
        for variant, engine in engines.items():
            decisions[variant] = engine.step(window_id, ahs_result["ahs"],
                                             harm if variant == "separated" else None)

        packet = alert_packet(window_id, results, ahs_result, harm,
                              decisions["separated"], registry)
        audit.record(window_id=window_id, window_meta=meta, results=results,
                     ahs_result=ahs_result, harm=harm,
                     governance=decisions, packet=packet)
        log.append({
            "window_id": window_id, "meta": meta, "ahs": ahs_result["ahs"],
            "ahs_declared_weights": ahs_result["ahs_declared_weights"],
            "ahs_renormalised": ahs_result["ahs_renormalised"],
            "missing_monitors": ahs_result["missing_monitors"],
            "weights": {k: v["weight_renormalised"] for k, v in ahs_result["components"].items()},
            "components": {k: v["contribution_renormalised"] for k, v in ahs_result["components"].items()},
            "violations": {k: v["violation_entering_ahs"] for k, v in ahs_result["components"].items()},
            "saturated": ahs_result["saturated_components"],
            "harm_level": harm["harm_level"],
            "states": {v: d["to_state"] for v, d in decisions.items()},
        })
        print(f"  {window_id}  n={meta['n']:>6,}  AHS={ahs_result['ahs']:.3f}  "
              f"harm={harm['harm_level']:<9}  sep={decisions['separated']['to_state']:<26}"
              f"col={decisions['collapsed']['to_state']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--monitors", default="configs/monitors.yaml")
    ap.add_argument("--registry", default="results/registry/EXP001_registry.json")
    ap.add_argument("--model", default="results/models/EXP001_frozen_model.joblib")
    ap.add_argument("--windows", type=int, default=10)
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    registry = json.loads(Path(args.registry).read_text())
    registry["monitor_config"] = load_config(args.monitors)
    registry["registry_version"] = "0.3.0"
    model = joblib.load(args.model)
    out = Path(args.outdir)

    features = registry["model"]["features"]["numeric"] + registry["model"]["features"]["categorical"]
    label = cfg["label"]["name"]
    splits = build_splits(cfg)
    reference, validation, deployment = splits.train, splits.validation, splits.target_sealed

    w = registry["monitor_config"]["ahs"]["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9, f"AHS weights must sum to 1, got {sum(w.values())}"

    print("[EXP003] measuring freeze-time baselines on in-distribution validation ...")
    registry["freeze_baselines"] = freeze_baselines(validation, reference, model, registry, features, label)
    for k, v in registry["freeze_baselines"].items():
        print(f"    {k}: {v['metric_key']} = {v['value']:.4f}")

    audit = AuditTrail(registry)
    report = {}

    # ---- Part A: OBSERVED, homogeneous stream ---------------------------------------
    print("\n[EXP003] Part A — OBSERVED: deployment domain, random partition "
          "(no time axis; stability test, not a trajectory)")
    engines = {v: GovernanceEngine(registry, variant=v)
               for v in registry["monitor_config"]["governance"]["variants"]}
    log_a: list = []
    process(replay.build("random_partition", df=deployment, n_windows=args.windows, seed=20260819),
            reference, model, registry, features, label, audit, engines, log_a)
    ahs_a = [w["ahs"] for w in log_a]
    report["part_a_observed"] = {
        "windows": log_a,
        "ahs_mean": float(np.mean(ahs_a)), "ahs_sd": float(np.std(ahs_a)),
        "ahs_range": [float(min(ahs_a)), float(max(ahs_a))],
        "governance": {v: e.summary() for v, e in engines.items()},
    }

    # ---- Part B: INJECTED, declared severity ramp ------------------------------------
    print("\n[EXP003] Part B — INJECTED: declared severity ramp with recovery")
    severities = [0.0, 0.0, 0.25, 0.50, 0.75, 1.00, 0.75, 0.25, 0.0, 0.0]
    base = deployment.sample(n=min(8000, len(deployment)), random_state=20260819)
    frames = [(f"R{i:02d}", perturb(base, s, seed=1000 + i, n_out=8000),
               {"evidence_class": "INJECTED", "severity": s}) for i, s in enumerate(severities)]
    engines_b = {v: GovernanceEngine(registry, variant=v)
                 for v in registry["monitor_config"]["governance"]["variants"]}
    log_b: list = []
    process(replay.build("sequence", frames=frames), reference, model, registry,
            features, label, audit, engines_b, log_b)

    ahs_b = [w["ahs"] for w in log_b]
    ramp = [(s, a) for s, a in zip(severities, ahs_b)][:6]
    monotone = all(ramp[i][1] >= ramp[i + 1][1] - 1e-9 for i in range(len(ramp) - 1))
    report["part_b_injected"] = {
        "severities": severities, "windows": log_b,
        "ahs_by_severity": ramp,
        "monotone_decreasing_on_ramp": monotone,
        "governance": {v: e.summary() for v, e in engines_b.items()},
    }

    print(f"\n[EXP003] AHS on ramp (severity -> AHS): "
          + ", ".join(f"{s:.2f}->{a:.3f}" for s, a in ramp))
    print(f"[EXP003] monotone decreasing on ramp: {monotone}")
    print("\n[EXP003] worked example — final ramp peak:")
    peak = max(range(len(log_b)), key=lambda i: 1 - log_b[i]["ahs"])
    print(explain({"ahs": log_b[peak]["ahs"], "deficit": 1 - log_b[peak]["ahs"],
                   "components": {k: {"contribution_renormalised": v,
                                      "violation_entering_ahs": log_b[peak]["violations"][k],
                                      "weight_renormalised": log_b[peak]["weights"][k],
                                      "saturated": k in log_b[peak]["saturated"]}
                                  for k, v in log_b[peak]["components"].items()},
                   "notes": []}))

    for part in ("part_a_observed", "part_b_injected"):
        sep = report[part]["governance"]["separated"]
        col = report[part]["governance"]["collapsed"]
        print(f"\n[EXP003] {part}: escalations separated={sep['escalations']} "
              f"collapsed={col['escalations']}; suspension reached "
              f"separated={sep['reached_suspension']} collapsed={col['reached_suspension']}")

    audit_path = audit.write(out / "audit" / f"{EXPERIMENT_ID}_audit.jsonl")
    write_json({
        "experiment_id": EXPERIMENT_ID,
        "environment": environment_record(),
        "config_hash": sha256_obj(cfg),
        "monitor_config_hash": sha256_obj(registry["monitor_config"]),
        "freeze_baselines": registry["freeze_baselines"],
        "audit_records": len(audit.records),
        **report,
    }, out / "metrics" / f"{EXPERIMENT_ID}_replay.json")
    write_json(registry, out / "registry" / f"{EXPERIMENT_ID}_registry.json")
    print(f"\n[EXP003] {len(audit.records)} audit records -> {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
