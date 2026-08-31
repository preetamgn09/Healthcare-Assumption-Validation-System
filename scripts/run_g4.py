"""EXP002 — Gate 4: run the A1, A3, calibration and fairness monitors.

    python scripts/run_g4.py

This is where the deployment-domain seal set at Gate 3 is broken. It is broken ONCE, for a
single reference-vs-deployment comparison, and the event is written into the registry's
validation history. It is not a replay: there is no time axis in D2, so there are no
windows and no detection-delay result. That comes from D1 (BRFSS) at Gate 5.

Three control comparisons run alongside the real one, because a monitor that fires on
everything is indistinguishable from a monitor that works:

    null      reference vs a held-out slice of the SAME distribution  -> expect no alert
    real      reference vs the deployment domain                      -> unknown
    injected  reference vs deployment with a known perturbation       -> expect an alert
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm.datasets.d2 import build_splits
from havm.monitors.distribution import monitor as a1_monitor
from havm.monitors.structural import calibration_monitor, fairness_monitor, structural_monitor
from havm.utils import environment_record, load_config, sha256_obj, write_json

EXPERIMENT_ID = "EXP002"


def load_registry(path: Path, monitor_cfg: dict) -> dict:
    registry = json.loads(path.read_text())
    registry["monitor_config"] = monitor_cfg          # ingested, then recorded with results
    registry["registry_version"] = "0.2.0"
    return registry


def run_monitor_set(name, window, reference, model, registry, features, label):
    probs = model.predict_proba(window[features])[:, 1]
    results = [
        a1_monitor(window, reference, registry),
        structural_monitor(window, registry),
        calibration_monitor(window[label].to_numpy(), probs, registry),
        fairness_monitor(window, probs, registry),
    ]
    return {"comparison": name, "n_window": len(window),
            "results": [r.to_dict() for r in results]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--monitors", default="configs/monitors.yaml")
    ap.add_argument("--registry", default="results/registry/EXP001_registry.json")
    ap.add_argument("--model", default="results/models/EXP001_frozen_model.joblib")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    registry = load_registry(Path(args.registry), load_config(args.monitors))
    model = joblib.load(args.model)
    out = Path(args.outdir)

    features = registry["model"]["features"]["numeric"] + registry["model"]["features"]["categorical"]
    label = cfg["label"]["name"]

    splits = build_splits(cfg)
    reference, validation, deployment = splits.train, splits.validation, splits.target_sealed

    # Seal check: the deployment set must be the same one Gate 3 sealed.
    expected_hash = registry["sealed_deployment_set"]["seal_hash"]
    actual_hash = sha256_obj(sorted(deployment["encounter_id"].tolist()))
    if actual_hash != expected_hash:
        print("SEAL BROKEN: the deployment set differs from the one recorded at Gate 3.",
              file=sys.stderr)
        return 1

    comparisons = []

    # (1) NULL CONTROL — same distribution. Any alert here is a false positive by construction.
    comparisons.append(run_monitor_set("null_control_validation", validation, reference,
                                       model, registry, features, label))

    # (2) REAL — the actual domain shift.
    comparisons.append(run_monitor_set("real_deployment_domain", deployment, reference,
                                       model, registry, features, label))

    # (3) INJECTED POSITIVE CONTROL — a declared perturbation with a known direction.
    #     Specified by its effect on the data-generating process (older, sicker case mix),
    #     not by the statistic it is meant to move (scope.md §8.3 point 4).
    rng = np.random.default_rng(20260819)
    injected = deployment.copy()
    older = injected["age"].isin(["[70-80)", "[80-90)", "[90-100)"])
    keep = np.where(older, 1.0, 0.35)                       # over-sample older admissions
    idx = rng.random(len(injected)) < keep
    injected = injected[idx].copy()
    injected["number_inpatient"] = injected["number_inpatient"] + 2   # higher prior utilisation
    comparisons.append(run_monitor_set("injected_case_mix_shift", injected, reference,
                                       model, registry, features, label))

    # ---- report ---------------------------------------------------------------------
    for block in comparisons:
        print(f"\n=== {block['comparison']}  (n={block['n_window']:,})")
        for r in block["results"]:
            flag = "TRIGGERED" if r["triggered"] else "ok       "
            print(f"  {flag}  {r['monitor']:<18} violation={r['violation']:.3f}  "
                  f"raw={ {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r['raw'].items() if not isinstance(v, dict)} }")

    registry.setdefault("validation_history", []).append({
        "experiment_id": EXPERIMENT_ID,
        "event": "DEPLOYMENT_SEAL_OPENED",
        "timestamp": environment_record()["timestamp_utc"],
        "reason": "Gate 4 single reference-vs-deployment monitor comparison",
        "seal_hash_verified": True,
    })
    write_json(registry, out / "registry" / f"{EXPERIMENT_ID}_registry.json")

    write_json({
        "experiment_id": EXPERIMENT_ID,
        "environment": environment_record(),
        "config_hash": sha256_obj(cfg),
        "monitor_config_hash": sha256_obj(registry["monitor_config"]),
        "reference": {"name": "train_source_non_emergency", "n": len(reference)},
        "comparisons": comparisons,
    }, out / "metrics" / f"{EXPERIMENT_ID}_monitors.json")

    print(f"\n[{EXPERIMENT_ID}] written to {out}/metrics/{EXPERIMENT_ID}_monitors.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
