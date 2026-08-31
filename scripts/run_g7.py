"""EXP007–EXP008 — Gate 7 (D2 portion).

    python scripts/run_g7.py

EXP007  RQ3 — the OOD bake-off. Six detectors scored against clinically defined OOD groups
        on real tabular EHR data. Ulmer et al. found uncertainty-based methods unreliable
        on exactly this modality; this is a replication attempt in a new direction.

EXP008  The complete seven-monitor AHS. EXP003 Finding 2 showed that three absent monitors
        raised AHS by 0.26 under declared weights — false reassurance produced by
        incompleteness. With A2, A4 and OOD implemented, that gap can be closed and the
        size of the correction measured directly.

OOD groups are defined by CLINICAL criteria fixed in advance, not by what the detectors
happen to find. Two of them are genuinely unseen in training rather than merely rare, which
is stated per group.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm.aggregation import compute_ahs, explain
from havm.datasets.d2 import build_splits
from havm.monitors.distribution import monitor as a1_monitor
from havm.monitors.ood import TabularOOD, ood_monitor
from havm.monitors.relational import operational_monitor, relational_monitor, simulate_batch
from havm.monitors.structural import calibration_monitor, fairness_monitor, structural_monitor
from havm.triage import assess_harm
from havm.utils import environment_record, load_config, sha256_obj, write_json

DETECTORS = ["mahalanobis", "knn", "isolation_forest", "predictive_entropy",
             "max_softmax", "energy"]
UNCERTAINTY_FAMILY = {"predictive_entropy", "max_softmax", "energy"}


def ood_groups(df, train_specialties):
    """Clinically defined OOD groups, declared before any detector is scored."""
    return {
        "paediatric_and_adolescent": (
            df["age"].isin(["[0-10)", "[10-20)"]),
            "age bands almost absent from the training population"),
        "unseen_admission_type": (
            df["admission_type_id"].astype(str) == "7",
            "admission type genuinely unseen in training (confirmed by the schema contract)"),
        "rare_specialty": (
            ~df["medical_specialty"].isin(train_specialties),
            "specialties outside the training vocabulary"),
        "extreme_prior_utilisation": (
            df["number_inpatient"] >= 5,
            "tail of prior inpatient admissions"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--monitors", default="configs/monitors.yaml")
    ap.add_argument("--registry", default="results/registry/EXP003_registry.json")
    ap.add_argument("--model", default="results/models/EXP001_frozen_model.joblib")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    registry = json.loads(Path(args.registry).read_text())
    registry["monitor_config"] = load_config(args.monitors)
    registry["registry_version"] = "0.4.0"
    model = joblib.load(args.model)
    out = Path(args.outdir)

    numeric = registry["model"]["features"]["numeric"]
    categorical = registry["model"]["features"]["categorical"]
    features = numeric + categorical
    label = cfg["label"]["name"]

    splits = build_splits(cfg)
    reference, validation, deployment = splits.train, splits.validation, splits.target_sealed
    train_specialties = splits.provenance["features"]["medical_specialty_vocabulary"]

    # ------------------------------------------------------------------ EXP007
    print("[EXP007] fitting six OOD detectors on the training reference ...")
    ood = TabularOOD(numeric, categorical).fit(reference, reference[label])

    ref_probs = model.predict_proba(reference[features])[:, 1]
    dep_probs = model.predict_proba(deployment[features])[:, 1]
    ref_scores = ood.scores(reference, ref_probs)
    dep_scores = ood.scores(deployment, dep_probs)

    groups = ood_groups(deployment, train_specialties)
    print(f"\n[EXP007] separating each OOD group from the rest of the deployment domain "
          f"(n={len(deployment):,})")
    header = "   {:<28}".format("group") + "".join(f"{d[:13]:>15}" for d in DETECTORS)
    print(header)
    exp007 = {}
    for gname, (mask, rationale) in groups.items():
        y = mask.to_numpy().astype(int)
        if y.sum() < 50 or y.sum() == len(y):
            continue
        row = {}
        for det in DETECTORS:
            row[det] = float(roc_auc_score(y, dep_scores[det]))
        exp007[gname] = {"n_in_group": int(y.sum()), "rationale": rationale, "auroc": row}
        print("   {:<28}".format(gname[:28]) + "".join(f"{row[d]:>15.3f}" for d in DETECTORS))

    means = {d: float(np.mean([g["auroc"][d] for g in exp007.values()])) for d in DETECTORS}
    ranking = sorted(means, key=means.get, reverse=True)
    print("\n   mean AUROC across groups: "
          + ", ".join(f"{d}={means[d]:.3f}" for d in ranking))

    unc = [means[d] for d in DETECTORS if d in UNCERTAINTY_FAMILY]
    dist = [means[d] for d in DETECTORS if d not in UNCERTAINTY_FAMILY]
    print(f"   uncertainty family mean {np.mean(unc):.3f}  |  "
          f"distance/density family mean {np.mean(dist):.3f}")
    near_chance = [d for d in DETECTORS if abs(means[d] - 0.5) < 0.10]
    print(f"   within 0.10 of chance: {near_chance or 'none'}")

    # ------------------------------------------------------------------ EXP008
    print("\n[EXP008] complete seven-monitor AHS on the deployment domain")
    detector = registry["monitor_config"]["monitors"]["ood"]["detector"]
    batch = simulate_batch("deployment", seed=1, delay_hours=0.0)

    all_results = [
        a1_monitor(deployment, reference, registry).to_dict(),
        relational_monitor(deployment[label].to_numpy(), dep_probs, ref_probs, registry,
                           labels_available=True).to_dict(),
        structural_monitor(deployment, registry).to_dict(),
        operational_monitor(batch, registry).to_dict(),
        ood_monitor(dep_scores[detector], ref_scores[detector], registry, detector).to_dict(),
        calibration_monitor(deployment[label].to_numpy(), dep_probs, registry).to_dict(),
        fairness_monitor(deployment, dep_probs, registry).to_dict(),
    ]

    registry["freeze_baselines"] = registry.get("freeze_baselines", {})
    full = compute_ahs(all_results, registry)
    partial = compute_ahs([r for r in all_results
                           if r["monitor"] in ("a1_distribution", "a3_structural",
                                               "calibration", "fairness")], registry)
    harm = assess_harm(all_results, full, registry)

    for r in all_results:
        flag = "TRIGGERED" if r["triggered"] else "ok       "
        print(f"   {flag}  {r['monitor']:<18} violation={r['violation']:.3f}  "
              f"[{r['evidence_class']}]")
    print(f"\n   four monitors  (Gate 5 configuration): AHS = {partial['ahs']:.3f}")
    print(f"   seven monitors (complete):              AHS = {full['ahs']:.3f}")
    print(f"   correction from completing the set:     {partial['ahs'] - full['ahs']:+.3f}")
    print(f"   harm level: {harm['harm_level']}")
    print("\n" + explain(full))

    # A2 with labels withheld, as a deployment would actually see it.
    a2_blind = relational_monitor(deployment[label].to_numpy(), dep_probs, ref_probs,
                                  registry, labels_available=False).to_dict()
    print(f"\n   A2 with labels available: violation {all_results[1]['violation']:.3f} "
          f"(AUROC {all_results[1]['raw']['auroc']:.4f}, "
          f"delta {all_results[1]['raw']['auroc_delta']:.4f})")
    print(f"   A2 label-blind (real-time): violation {a2_blind['violation']:.3f} "
          f"— score PSI only")

    write_json({
        "experiment_ids": ["EXP007", "EXP008"],
        "environment": environment_record(),
        "config_hash": sha256_obj(cfg),
        "monitor_config_hash": sha256_obj(registry["monitor_config"]),
        "exp007_ood_bakeoff": {
            "groups": exp007, "mean_auroc": means, "ranking": ranking,
            "uncertainty_family_mean": float(np.mean(unc)),
            "distance_density_family_mean": float(np.mean(dist)),
            "within_0.10_of_chance": near_chance,
            "energy_note": "computed on a logistic regression fitted to the same features; "
                           "the frozen gradient-boosted model produces no logit vector",
        },
        "exp008_complete_ahs": {
            "monitors": all_results,
            "ahs_four_monitors": partial["ahs"],
            "ahs_seven_monitors": full["ahs"],
            "correction": partial["ahs"] - full["ahs"],
            "components": {k: v["contribution_renormalised"] for k, v in full["components"].items()},
            "harm_assessment": harm,
            "a2_label_blind": a2_blind,
            "notes": full["notes"],
        },
    }, out / "metrics" / "EXP007-008_ood_and_full_ahs.json")
    write_json(registry, out / "registry" / "EXP008_registry.json")
    print(f"\n[G7] written to {out}/metrics/EXP007-008_ood_and_full_ahs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
