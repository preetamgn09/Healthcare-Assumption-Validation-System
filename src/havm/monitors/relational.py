"""A2 (relational) and A4 (operational) monitors.

A2 — Relational assumption:  P_train(Y|X) ≈ P_deploy(Y|X)

    Two signals, because in a real deployment only one of them is available at monitoring
    time:

      score_psi       drift in the distribution of predicted scores. LABEL-FREE, available
                      immediately. Cannot distinguish covariate shift from concept drift on
                      its own — a change in P(X) moves scores too.
      auroc_delta     loss of discrimination against the frozen validation value.
                      LABEL-DEPENDENT, and therefore only available after outcomes are
                      observed. A `label_delay_windows` setting makes that lag explicit
                      rather than pretending labels arrive with the data.

    The distinction matters for every claim about detection speed: a monitor that silently
    uses labels the deployment would not yet have is an oracle, not a monitor.

A4 — Operational assumption: the deployment environment stays consistent.

    No public dataset carries pipeline telemetry. Operational events are therefore
    SIMULATED and labelled as such wherever they appear (BRIEF §52). The simulator produces
    a batch record; the monitor reads it. Nothing here is evidence about real infrastructure.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

from havm.monitors.base import MonitorResult, normalise
from havm.monitors.distribution import population_stability_index

import pandas as pd


# ------------------------------------------------------------------------ A2
def relational_monitor(y_true, y_prob, reference_probs, registry: dict,
                       labels_available: bool = True) -> MonitorResult:
    cfg = registry["monitor_config"]["monitors"]["a2_relational"]
    norm = registry["monitor_config"]["normalisation"]["method"]

    score_psi = population_stability_index(
        pd.Series(reference_probs), pd.Series(np.asarray(y_prob)),
        cfg["psi_bins"], categorical=False,
    )

    baseline_auroc = cfg.get("baseline_auroc")
    auroc = auroc_delta = None
    notes = []
    if labels_available and baseline_auroc is not None:
        y_true = np.asarray(y_true)
        if 0 < y_true.sum() < len(y_true):
            auroc = float(roc_auc_score(y_true, y_prob))
            auroc_delta = max(baseline_auroc - auroc, 0.0)
    else:
        notes.append(
            f"Labels withheld ({cfg['label_delay_windows']}-window delay declared). "
            "Only the label-free score-distribution signal is available; discrimination "
            "loss cannot be observed yet."
        )

    v_score = normalise(score_psi, cfg["score_psi_threshold"], norm)
    v_auroc = normalise(auroc_delta, cfg["auroc_delta_threshold"], norm) if auroc_delta is not None else 0.0
    violation = max(v_score, v_auroc)

    notes.append("Score drift alone cannot separate covariate shift from concept drift: a "
                 "change in P(X) moves predicted scores without any change in P(Y|X).")

    return MonitorResult(
        monitor="a2_relational",
        assumption="A2",
        evidence_class="OBSERVED",
        raw={"score_psi": score_psi, "auroc": auroc, "auroc_delta": auroc_delta,
             "baseline_auroc": baseline_auroc, "labels_available": labels_available},
        threshold={"score_psi": cfg["score_psi_threshold"],
                   "auroc_delta": cfg["auroc_delta_threshold"]},
        violation=violation,
        triggered=(score_psi >= cfg["score_psi_threshold"])
                  or (auroc_delta is not None and auroc_delta >= cfg["auroc_delta_threshold"]),
        evidence={"label_free_violation": v_score, "label_dependent_violation": v_auroc},
        notes=notes,
    )


# ------------------------------------------------------------------------ A4
def simulate_batch(window_id: str, *, seed: int, missing: bool = False, delay_hours: float = 0.0,
                   latency_ms: float | None = None, schema_version: str = "v1",
                   pipeline_version: str = "1.0.0") -> dict:
    """Produce a SIMULATED operational record for one batch.

    This is invented infrastructure telemetry. It exists so the A4 monitor can be built and
    tested; it is not, and must never be described as, deployment evidence."""
    rng = np.random.default_rng(seed)
    return {
        "window_id": window_id,
        "evidence_class": "SIMULATED",
        "batch_received": not missing,
        "delay_hours": float(delay_hours),
        "latency_ms": float(latency_ms if latency_ms is not None else rng.normal(120, 15)),
        "schema_version": schema_version,
        "pipeline_version": pipeline_version,
    }


def operational_monitor(batch: dict, registry: dict) -> MonitorResult:
    cfg = registry["monitor_config"]["monitors"]["a4_operational"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    expected = cfg["expected"]

    faults, worst = {}, 0.0
    if not batch.get("batch_received", True):
        faults["missing_batch"] = True
        worst = 1.0
    delay = batch.get("delay_hours", 0.0)
    if delay >= cfg["delay_hours_threshold"]:
        faults["delayed_batch"] = delay
        worst = max(worst, normalise(delay, cfg["delay_hours_threshold"], norm))
    latency = batch.get("latency_ms", 0.0)
    if latency >= cfg["latency_ms_threshold"]:
        faults["latency"] = latency
        worst = max(worst, normalise(latency, cfg["latency_ms_threshold"], norm))
    for key in ("schema_version", "pipeline_version"):
        if batch.get(key) != expected[key]:
            faults[f"{key}_changed"] = {"expected": expected[key], "observed": batch.get(key)}
            worst = 1.0

    return MonitorResult(
        monitor="a4_operational",
        assumption="A4",
        evidence_class="SIMULATED",
        raw={"faults": list(faults), "delay_hours": delay, "latency_ms": latency,
             "batch_received": batch.get("batch_received", True)},
        threshold={"delay_hours": cfg["delay_hours_threshold"],
                   "latency_ms": cfg["latency_ms_threshold"], "expected": expected},
        violation=min(worst, 1.0),
        triggered=bool(faults),
        evidence={"batch": batch, "faults": faults},
        notes=["SIMULATED OPERATIONAL EVIDENCE. No public dataset carries pipeline "
               "telemetry; these events were generated, not observed."],
    )
