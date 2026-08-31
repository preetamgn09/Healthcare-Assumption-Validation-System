"""EXP001 — Gate 3: data pipeline, baselines, model freeze.

    python scripts/run_g3.py --config configs/d2_diabetes.yaml

Produces, under results/:
    metrics/EXP001_baselines.json    every candidate's source-validation metrics
    models/EXP001_frozen_model.joblib + model_card.json
    registry/EXP001_registry.json    the L2 assumption registry at freeze time

The deployment (target) domain is SEALED here: its row count and hash are recorded, but
no label, metric or model-selection decision touches it. That seal is what makes the
Gate 5 replay a deployment simulation rather than a retrospective fit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm.datasets.d2 import build_splits
from havm.features import feature_columns
from havm.metrics import core_metrics, rates_at_threshold, subgroup_metrics
from havm.models import fit_predict
from havm.registry import build_registry, save
from havm.schema import fit_schema, validate
from havm.utils import environment_record, load_config, sha256_file, sha256_obj, write_json

EXPERIMENT_ID = "EXP001"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out = Path(args.outdir)
    env = environment_record()
    numeric = cfg["features"]["numeric"]
    categorical = cfg["features"]["categorical"]
    label = cfg["label"]["name"]
    seed = cfg["models"]["seed"]

    print(f"[{EXPERIMENT_ID}] building splits ...")
    splits = build_splits(cfg)
    train, validation, target = splits.train, splits.validation, splits.target_sealed

    # ---- schema contract, fitted on training only -----------------------------------
    schema = fit_schema(train, cfg)
    self_check = validate(train, schema)
    assert not self_check, f"schema must validate against its own training data: {self_check}"
    val_violations = validate(validation, schema)

    # ---- candidates -----------------------------------------------------------------
    results, fitted = {}, {}
    for name in cfg["models"]["candidates"]:
        print(f"[{EXPERIMENT_ID}] fitting {name} ...")
        model, probs = fit_predict(name, train, validation, numeric, categorical, label, seed)
        m = core_metrics(validation[label], probs)
        # Operating point: flag the top decile of predicted risk — a workload-anchored
        # choice, not an optimised one. POLICY, to be varied later.
        thr = float(np.quantile(probs, 0.90))
        m["operating_point"] = rates_at_threshold(validation[label], probs, thr)
        m["subgroups"] = subgroup_metrics(validation, label, probs, cfg["subgroups"], thr)
        results[name], fitted[name] = m, model
        print(f"    AUROC {m['auroc']:.4f}  AUPRC {m['auprc']:.4f}  "
              f"Brier {m['brier']:.4f}  ECE {m['ece']:.4f}")

    # ---- selection, on source validation only ---------------------------------------
    metric = cfg["models"]["selection_metric"]
    selected = max(results, key=lambda k: results[k][metric])
    print(f"[{EXPERIMENT_ID}] selected: {selected} (by {metric} on source validation)")

    # ---- freeze ---------------------------------------------------------------------
    out.joinpath("models").mkdir(parents=True, exist_ok=True)
    model_path = out / "models" / f"{EXPERIMENT_ID}_frozen_model.joblib"
    joblib.dump(fitted[selected], model_path)

    model_card = {
        "model_id": f"d2_readmit30_{selected}",
        "model_version": "1.0.0-frozen",
        "experiment_id": EXPERIMENT_ID,
        "algorithm": selected,
        "selected_by": f"{metric} on source-domain validation",
        "frozen": True,
        "retraining_policy": "NONE during the primary monitoring experiment (BRIEF §49)",
        "artifact": str(model_path),
        "artifact_sha256": sha256_file(model_path),
        "features": {"numeric": numeric, "categorical": categorical},
        "training_domain": cfg["domain"]["source_name"],
        "deployment_domain": cfg["domain"]["target_name"],
        "validation_metrics": {k: v for k, v in results[selected].items()
                               if k not in ("calibration_bins", "subgroups")},
        "environment": env,
        "seed": seed,
    }
    write_json(model_card, out / "models" / f"{EXPERIMENT_ID}_model_card.json")

    # ---- sealed deployment set ------------------------------------------------------
    gcol = cfg["split"]["group_column"]
    sealed = {
        "n_encounters": int(len(target)),
        "n_patients": int(target[gcol].nunique()),
        "seal_hash": sha256_obj(sorted(target["encounter_id"].tolist())),
        "labels_inspected_at_gate3": False,
        "note": "Opened at G5 for deployment replay. Any earlier metric on this set invalidates the experiment.",
    }

    write_json({
        "experiment_id": EXPERIMENT_ID,
        "config_file": args.config,
        "config_hash": sha256_obj(cfg),
        "environment": env,
        "provenance": splits.provenance,
        "schema_self_check_violations": self_check,
        "schema_violations_on_validation": val_violations,
        "candidates": results,
        "selected_model": selected,
        "sealed_deployment_set": sealed,
    }, out / "metrics" / f"{EXPERIMENT_ID}_baselines.json")

    registry = build_registry(
        model_card=model_card, schema=schema, provenance=splits.provenance, cfg=cfg,
    )
    registry["sealed_deployment_set"] = sealed
    save(registry, out / "registry" / f"{EXPERIMENT_ID}_registry.json")

    print(f"[{EXPERIMENT_ID}] wrote results to {out}/  (registry {registry['registry_hash'][:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
