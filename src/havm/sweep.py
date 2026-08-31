"""Sensitivity sweep machinery.

The expensive part of monitoring is computing raw metrics; the cheap part is turning them
into violations, an AHS and a governance state. Every question in Gate 6 — thresholds,
weights, normalisation, ablation — varies only the cheap part. So raw metrics are computed
ONCE per window and rescored under each policy. This is what makes a grid of hundreds of
configurations affordable, and it also guarantees every configuration is compared on
identical measurements rather than on separate monitor runs.

    collect(...)  ->  one raw record per window
    rescore(...)  ->  violations, AHS and an alert decision for a given policy
    evaluate(...) ->  precision / recall / false-alarm rate against declared ground truth
"""
from __future__ import annotations

import numpy as np

from havm.monitors.base import normalise

# Which raw metric drives each monitor's violation, and which declared bound it is
# compared against. a3_structural is already a fraction on [0,1] and needs no threshold.
METRIC_SPEC = {
    "a1_distribution": ("max_psi", "psi"),
    "calibration": ("ece", "ece"),
    "fairness": ("max_delta_tpr", "delta_tpr"),
    "a3_structural": (None, None),
}


def raw_metric(result: dict) -> float:
    name = result["monitor"]
    key, _ = METRIC_SPEC[name]
    if key is None:
        total = result["raw"].get("n_columns_total") or 1
        return result["raw"].get("n_columns_affected", 0) / total
    return float(result["raw"].get(key, 0.0))


def rescore(results: list[dict], *, weights: dict, normalisation: str, thresholds: dict,
            baselines: dict, entry_mode: dict, ahs_band: float,
            null_quantiles: dict | None = None, ablate: set[str] | None = None) -> dict:
    """Recompute violations, AHS and the alert decision under one policy."""
    ablate = ablate or set()
    active = {r["monitor"]: r for r in results if r["monitor"] not in ablate}
    available_weight = sum(weights.get(m, 0.0) for m in active)

    components, deficit, triggered_any = {}, 0.0, False
    for name, result in active.items():
        w = weights.get(name, 0.0)
        if w == 0.0:
            continue
        metric = raw_metric(result)
        threshold_key = METRIC_SPEC[name][1]
        threshold = result["threshold"].get(threshold_key) if threshold_key else 1.0
        threshold = thresholds.get(name, threshold)

        if entry_mode.get(name) == "baseline_relative" and name in baselines:
            metric = max(metric - baselines[name], 0.0)

        if normalisation == "empirical_quantile" and not (null_quantiles and name in null_quantiles):
            # No null distribution was calibrated for this monitor. Falling back to the
            # threshold rule is the only honest option: inventing a quantile from nothing
            # would put a fabricated number into the AHS.
            v = normalise(metric, threshold, "threshold_relative")
        elif normalisation == "empirical_quantile":
            # Position of this metric within the null distribution observed on calibration
            # windows. Answers "how unusual is this against no-change data", which is a
            # different question from "how far past an asserted bound is this".
            null = null_quantiles[name]
            v = float(np.clip(np.searchsorted(null, metric) / max(len(null), 1), 0.0, 1.0))
        else:
            v = normalise(metric, threshold, normalisation)

        if threshold and metric >= threshold:
            triggered_any = True
        w_renorm = w / available_weight if available_weight else 0.0
        deficit += w_renorm * v
        components[name] = {"metric": metric, "violation": v, "weight": w_renorm,
                            "contribution": w_renorm * v, "saturated": v >= 1.0}

    ahs = max(0.0, min(1.0, 1.0 - deficit))
    return {"ahs": ahs, "components": components,
            "alert_ahs": ahs < ahs_band,
            "alert_or_rule": triggered_any,
            "saturated": [n for n, c in components.items() if c["saturated"]]}


def evaluate(decisions: list[bool], truth: list[int]) -> dict:
    d = np.asarray(decisions, dtype=int)
    y = np.asarray(truth, dtype=int)
    tp = int(((d == 1) & (y == 1)).sum())
    fp = int(((d == 1) & (y == 0)).sum())
    fn = int(((d == 0) & (y == 1)).sum())
    tn = int(((d == 0) & (y == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall and (precision + recall) else None)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1,
            "false_alarm_rate": fp / (fp + tn) if (fp + tn) else None,
            "alert_rate": float(d.mean())}
