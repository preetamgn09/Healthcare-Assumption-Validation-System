"""Evaluation metrics for the monitored model.

ECE is implemented here rather than imported because later stages need the bin-level
detail, and because BRIEF §38 requires it to satisfy analytic tests (perfect calibration
=> ECE -> 0). Equal-width binning is used; the bin count is a POLICY choice and is
recorded with every result.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def expected_calibration_error(y_true, y_prob, n_bins: int = 10) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, edges[1:-1], right=False), 0, n_bins - 1)

    ece, bins = 0.0, []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        if n == 0:
            continue
        conf, acc = float(y_prob[m].mean()), float(y_true[m].mean())
        ece += (n / len(y_true)) * abs(acc - conf)
        bins.append({"bin": b, "n": n, "mean_predicted": conf, "observed_rate": acc})
    return {"ece": float(ece), "n_bins": n_bins, "bins": bins}


def core_metrics(y_true, y_prob, n_bins: int = 10) -> dict:
    y_true = np.asarray(y_true)
    cal = expected_calibration_error(y_true, y_prob, n_bins)
    return {
        "n": int(len(y_true)),
        "prevalence": float(np.mean(y_true)),
        "auroc": float(roc_auc_score(y_true, y_prob)),
        "auprc": float(average_precision_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "ece": cal["ece"],
        "calibration_bins": cal["bins"],
    }


def rates_at_threshold(y_true, y_prob, threshold: float) -> dict:
    y_true = np.asarray(y_true).astype(int)
    pred = (np.asarray(y_prob) >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    return {
        "threshold": threshold,
        "tpr": tp / (tp + fn) if (tp + fn) else None,
        "fpr": fp / (fp + tn) if (fp + tn) else None,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "n_flagged": tp + fp,
    }


def subgroup_metrics(df, y_true_col, y_prob, subgroup_cfg: dict, threshold: float) -> dict:
    """Per-subgroup rates, gated on a declared minimum group size.

    Groups below the minimum are reported as suppressed rather than silently omitted:
    an unstable estimate presented as a number is worse than an acknowledged gap.
    """
    out = {}
    min_n = subgroup_cfg["min_group_size"]
    attributes = subgroup_cfg["attributes"]

    for attr in attributes:
        out[attr] = {}
        for value, block in df.groupby(attr, observed=True):
            mask = df[attr] == value
            n = int(mask.sum())
            if n < min_n:
                out[attr][str(value)] = {"n": n, "suppressed": True, "reason": "below min_group_size"}
                continue
            yt = block[y_true_col].to_numpy()
            yp = np.asarray(y_prob)[mask.to_numpy()]
            entry = {"n": n, "prevalence": float(yt.mean()), "suppressed": False}
            entry.update(rates_at_threshold(yt, yp, threshold))
            if 0 < yt.sum() < len(yt):
                entry["auroc"] = float(roc_auc_score(yt, yp))
                entry["ece"] = expected_calibration_error(yt, yp)["ece"]
            out[attr][str(value)] = entry
    return out
