"""A3 (structural), calibration, and fairness monitors.

Kept in one module because each is short and they share no machinery worth separating.
All three read their configuration from the registry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from havm.metrics import expected_calibration_error, rates_at_threshold
from havm.monitors.base import MonitorResult, normalise
from havm.schema import validate


# --------------------------------------------------------------------- A3 structural
def structural_monitor(window: pd.DataFrame, registry: dict) -> MonitorResult:
    """Schema conformance, missingness drift, and vocabulary growth.

    Runs against the schema contract in the registry and needs no model and no labels —
    it is the one monitor that would still work if the model were removed entirely, which
    is why the brief (§5, A3) requires it to be model-independent.
    """
    cfg = registry["monitor_config"]["monitors"]["a3_structural"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    schema = registry["feature_expectations"]

    violations = validate(window, schema)

    missingness, cardinality = {}, {}
    for col, spec in schema["columns"].items():
        if col not in window.columns:
            continue
        if spec["kind"] == "numeric":
            rate = float(pd.to_numeric(window[col], errors="coerce").isna().mean())
        else:
            rate = float(window[col].isna().mean())
        delta = rate - spec["missing_rate"]
        if abs(delta) >= cfg["missingness_delta_threshold"]:
            missingness[col] = {"reference": spec["missing_rate"], "current": rate, "delta": delta}
        if spec["kind"] == "categorical":
            growth = (window[col].nunique() - spec["cardinality"]) / max(spec["cardinality"], 1)
            if growth >= cfg["cardinality_growth_threshold"]:
                cardinality[col] = {"reference": spec["cardinality"],
                                    "current": int(window[col].nunique()), "growth": float(growth)}

    n_columns = len(schema["columns"])
    n_affected = len({v["column"] for v in violations} | set(missingness) | set(cardinality))
    # Fraction of the contract that is broken. Already on [0,1] — no threshold division.
    violation = normalise(n_affected / n_columns if n_columns else 0.0, 1.0, "linear_clip")

    return MonitorResult(
        monitor="a3_structural",
        assumption="A3",
        evidence_class="OBSERVED",
        raw={"n_schema_violations": len(violations),
             "n_columns_missingness_shift": len(missingness),
             "n_columns_cardinality_growth": len(cardinality),
             "n_columns_affected": n_affected, "n_columns_total": n_columns},
        threshold={"missingness_delta": cfg["missingness_delta_threshold"],
                   "cardinality_growth": cfg["cardinality_growth_threshold"]},
        violation=violation,
        triggered=n_affected > 0,
        evidence={"schema_violations": violations, "missingness": missingness,
                  "cardinality": cardinality},
    )


# --------------------------------------------------------------------- calibration
def calibration_monitor(y_true, y_prob, registry: dict) -> MonitorResult:
    cfg = registry["monitor_config"]["monitors"]["calibration"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    cal = expected_calibration_error(y_true, y_prob, cfg["n_bins"])
    ece = cal["ece"]

    return MonitorResult(
        monitor="calibration",
        assumption="calibration",
        evidence_class="OBSERVED",
        raw={"ece": ece, "mean_predicted": float(np.mean(y_prob)),
             "observed_rate": float(np.mean(y_true))},
        threshold={"ece": cfg["ece_threshold"], "n_bins": cfg["n_bins"]},
        violation=normalise(ece, cfg["ece_threshold"], norm),
        triggered=ece >= cfg["ece_threshold"],
        evidence={"bins": cal["bins"]},
        notes=["Requires outcome labels, which a live deployment would not have at "
               "monitoring time. Treated here as a retrospective measurement, not as a "
               "signal available in real time."],
    )


# --------------------------------------------------------------------- fairness
def fairness_monitor(window: pd.DataFrame, y_prob, registry: dict) -> MonitorResult:
    """Subgroup TPR/FPR disparity at a declared operating point.

    Groups below the declared minimum size are suppressed rather than estimated: an
    unstable rate presented as a number is worse than an acknowledged gap, and the
    suppression itself is reported so the reader can see what was not measured.
    """
    cfg = registry["monitor_config"]["monitors"]["fairness"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    label = registry["label_definition"]["name"]
    attributes = registry["subgroups"]["attributes"]
    min_n = registry["subgroups"]["min_group_size"]

    y_prob = np.asarray(y_prob)
    threshold = float(np.quantile(y_prob, cfg["operating_point_quantile"]))

    min_pos = cfg.get("min_positives", 0)

    per_attribute, suppressed = {}, {}
    worst_dtpr = worst_dfpr = 0.0
    worst_pair = None
    null_bands = {}

    for attr in attributes:
        groups, skipped = {}, []
        for value, block in window.groupby(attr, observed=True):
            mask = (window[attr] == value).to_numpy()
            n_pos = int(block[label].sum())
            if mask.sum() < min_n or n_pos < min_pos:
                skipped.append({"group": str(value), "n": int(mask.sum()), "n_positive": n_pos,
                                "gate": "min_group_size" if mask.sum() < min_n else "min_positives"})
                continue
            r = rates_at_threshold(block[label].to_numpy(), y_prob[mask], threshold)
            r["n"] = int(mask.sum())
            r["n_positive"] = n_pos
            r["prevalence"] = float(block[label].mean())
            groups[str(value)] = r
        if len(groups) >= 2:
            tprs = {g: v["tpr"] for g, v in groups.items() if v["tpr"] is not None}
            fprs = {g: v["fpr"] for g, v in groups.items() if v["fpr"] is not None}
            dtpr = max(tprs.values()) - min(tprs.values()) if len(tprs) >= 2 else 0.0
            dfpr = max(fprs.values()) - min(fprs.values()) if len(fprs) >= 2 else 0.0
            per_attribute[attr] = {"groups": groups, "delta_tpr": dtpr, "delta_fpr": dfpr}
            if dtpr > worst_dtpr:
                worst_dtpr, worst_pair = dtpr, (attr, max(tprs, key=tprs.get), min(tprs, key=tprs.get))
            worst_dfpr = max(worst_dfpr, dfpr)
        else:
            per_attribute[attr] = {"groups": groups, "delta_tpr": None, "delta_fpr": None,
                                   "reason": "fewer than two groups above min_group_size"}
        if skipped:
            suppressed[attr] = skipped

    # Permutation reference band. Shuffling group membership breaks any association
    # between group and model error while preserving group sizes, so the resulting
    # distribution of max ΔTPR is what sampling noise alone produces. A disparity inside
    # this band is not evidence of anything, whatever the declared threshold says.
    nb = cfg.get("null_band", {})
    if nb.get("enabled"):
        rng = np.random.default_rng(nb["seed"])
        y_true_all = window[label].to_numpy()
        for attr in attributes:
            observed_groups = list(per_attribute.get(attr, {}).get("groups", {}))
            if len(observed_groups) < 2:
                continue
            assign = window[attr].astype(str).to_numpy()
            eligible = np.isin(assign, observed_groups)
            yt, yp, ga = y_true_all[eligible], y_prob[eligible], assign[eligible]
            draws = []
            for _ in range(nb["n_permutations"]):
                shuffled = rng.permutation(ga)
                tprs = []
                for g in observed_groups:
                    m = shuffled == g
                    r = rates_at_threshold(yt[m], yp[m], threshold)
                    if r["tpr"] is not None:
                        tprs.append(r["tpr"])
                if len(tprs) >= 2:
                    draws.append(max(tprs) - min(tprs))
            if draws:
                band = float(np.percentile(draws, nb["percentile"]))
                obs = per_attribute[attr]["delta_tpr"]
                null_bands[attr] = {
                    "delta_tpr_observed": obs,
                    f"null_p{nb['percentile']}": band,
                    "exceeds_null_band": bool(obs is not None and obs > band),
                    "n_permutations": nb["n_permutations"],
                }

    v_tpr = normalise(worst_dtpr, cfg["delta_tpr_threshold"], norm)
    v_fpr = normalise(worst_dfpr, cfg["delta_fpr_threshold"], norm)

    notes = ["Disparities are uncorrected for case mix: a prevalence difference between "
             "groups can produce a rate difference without any model behaviour being at "
             "fault. Distinguishing the two is a harm-assessment question for triage (G5), "
             "not something this monitor can settle."]
    if suppressed:
        notes.append(f"Suppressed groups below n={min_n}: "
                     + "; ".join(f"{a}: {[s['group'] for s in v]}" for a, v in suppressed.items()))

    return MonitorResult(
        monitor="fairness",
        assumption="fairness",
        evidence_class="OBSERVED",
        raw={"max_delta_tpr": worst_dtpr, "max_delta_fpr": worst_dfpr,
             "worst_pair": worst_pair, "operating_threshold": threshold,
             "exceeds_null_band": any(v["exceeds_null_band"] for v in null_bands.values())
             if null_bands else None},
        threshold={"delta_tpr": cfg["delta_tpr_threshold"], "delta_fpr": cfg["delta_fpr_threshold"],
                   "min_group_size": min_n, "min_positives": min_pos},
        violation=max(v_tpr, v_fpr),
        triggered=(worst_dtpr >= cfg["delta_tpr_threshold"]) or (worst_dfpr >= cfg["delta_fpr_threshold"]),
        evidence={"per_attribute": per_attribute, "suppressed": suppressed,
                  "null_bands": null_bands},
        notes=notes,
    )
