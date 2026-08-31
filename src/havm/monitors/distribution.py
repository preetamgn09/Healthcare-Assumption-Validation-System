"""A1 — Distributional assumption:  P_train(X) ≈ P_deploy(X).

Three signals, deliberately kept separate because they answer different questions:

  PSI          effect size, per feature. "How much has this moved?"
  KS / chi²    statistical significance, per feature, BH-FDR corrected.
               "Could this have happened by chance?"
  MMD          a single multivariate statistic over the numeric block. "Has the joint
               distribution moved, including in ways no single feature reveals?"

BRIEF §5 requires distinguishing statistically significant from practically meaningful
drift. At deployment-scale n those two answers diverge sharply — a trivial shift is
significant at n=50,000 — so both are reported and the divergence is measured rather than
resolved by picking one. The violation signal is driven by PSI (effect size); significance
is carried as evidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from havm.monitors.base import MonitorResult, benjamini_hochberg, normalise

EPS = 1e-6


def population_stability_index(ref: pd.Series, cur: pd.Series, bins: int, categorical: bool) -> float:
    """PSI = Σ (p_cur - p_ref) · ln(p_cur / p_ref). Bins are fixed on the REFERENCE."""
    if categorical:
        categories = sorted(set(ref.astype(str)) | set(cur.astype(str)))
        p_ref = ref.astype(str).value_counts(normalize=True).reindex(categories).fillna(0.0).to_numpy()
        p_cur = cur.astype(str).value_counts(normalize=True).reindex(categories).fillna(0.0).to_numpy()
    else:
        r = pd.to_numeric(ref, errors="coerce").dropna()
        c = pd.to_numeric(cur, errors="coerce").dropna()
        quantiles = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)))
        if len(quantiles) < 3:            # degenerate / near-constant feature
            return 0.0
        edges = np.concatenate([[-np.inf], quantiles[1:-1], [np.inf]])
        p_ref = np.histogram(r, bins=edges)[0] / len(r)
        p_cur = np.histogram(c, bins=edges)[0] / len(c)

    p_ref = np.clip(p_ref, EPS, None)
    p_cur = np.clip(p_cur, EPS, None)
    return float(np.sum((p_cur - p_ref) * np.log(p_cur / p_ref)))


def linear_mmd(X: np.ndarray, Y: np.ndarray, seed: int, max_samples: int) -> dict:
    """Unbiased linear-time MMD² with an RBF kernel (median-heuristic bandwidth).

    The quadratic-form estimator is O(n²) and unaffordable once this runs per window over a
    replay; the linear estimator trades variance for a cost that scales. It is unbiased, so
    it can be slightly NEGATIVE when the two samples are drawn from the same distribution —
    that is correct behaviour, not a bug, and the raw value is reported unclipped.
    """
    rng = np.random.default_rng(seed)
    n = min(len(X), len(Y), max_samples)
    n -= n % 2                                    # the estimator consumes pairs
    if n < 4:
        return {"mmd2": 0.0, "n_used": 0, "bandwidth": None}
    X = X[rng.choice(len(X), n, replace=False)]
    Y = Y[rng.choice(len(Y), n, replace=False)]

    probe = X[rng.choice(n, min(n, 1000), replace=False)]
    d2 = np.sum((probe[:, None, :] - probe[None, :, :]) ** 2, axis=-1)
    median_sq = np.median(d2[d2 > 0]) if np.any(d2 > 0) else 1.0
    gamma = 1.0 / max(median_sq, EPS)

    x1, x2, y1, y2 = X[0::2], X[1::2], Y[0::2], Y[1::2]
    k = lambda a, b: np.exp(-gamma * np.sum((a - b) ** 2, axis=1))
    h = k(x1, x2) + k(y1, y2) - k(x1, y2) - k(x2, y1)
    return {"mmd2": float(np.mean(h)), "n_used": int(n), "bandwidth_gamma": float(gamma)}


def monitor(window: pd.DataFrame, reference: pd.DataFrame, registry: dict) -> MonitorResult:
    cfg = registry["monitor_config"]["monitors"]["a1_distribution"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    numeric = registry["model"]["features"]["numeric"]
    categorical = registry["model"]["features"]["categorical"]

    per_feature, pvalues, names = {}, [], []
    for col in numeric + categorical:
        is_cat = col in categorical
        psi = population_stability_index(reference[col], window[col], cfg["psi_bins"], is_cat)
        if is_cat:
            cats = sorted(set(reference[col].astype(str)) | set(window[col].astype(str)))
            obs = window[col].astype(str).value_counts().reindex(cats).fillna(0).to_numpy()
            exp = reference[col].astype(str).value_counts(normalize=True).reindex(cats).fillna(0).to_numpy()
            exp = np.clip(exp, EPS, None) * obs.sum()
            exp = exp / exp.sum() * obs.sum()
            stat, p = stats.chisquare(obs, exp)
            test = "chi2"
        else:
            stat, p = stats.ks_2samp(
                pd.to_numeric(reference[col], errors="coerce").dropna(),
                pd.to_numeric(window[col], errors="coerce").dropna(),
            )
            test = "ks"
        per_feature[col] = {"psi": psi, "test": test, "statistic": float(stat), "p_value": float(p)}
        pvalues.append(float(p))
        names.append(col)

    rejected = benjamini_hochberg(pvalues, cfg["ks_alpha"])
    for col, rej in zip(names, rejected):
        per_feature[col]["significant_fdr"] = bool(rej)

    psis = {c: v["psi"] for c, v in per_feature.items()}
    max_psi = max(psis.values())
    worst = max(psis, key=psis.get)
    n_material = sum(v >= cfg["psi_threshold"] for v in psis.values())
    n_moderate = sum(cfg["psi_minor_threshold"] <= v < cfg["psi_threshold"] for v in psis.values())
    n_significant = sum(rejected)

    mmd = {}
    if cfg["mmd"]["enabled"]:
        ref_num = reference[numeric].to_numpy(dtype=float)
        cur_num = window[numeric].to_numpy(dtype=float)
        mu, sd = ref_num.mean(0), np.clip(ref_num.std(0), EPS, None)
        mmd = linear_mmd((ref_num - mu) / sd, (cur_num - mu) / sd,
                         cfg["mmd"]["seed"], cfg["mmd"]["max_samples"])

    violation = normalise(max_psi, cfg["psi_threshold"], norm)
    notes = []
    if n_significant > n_material:
        notes.append(
            f"{n_significant}/{len(names)} features are statistically significant under "
            f"FDR but only {n_material} exceed the PSI threshold. At this sample size "
            "significance is not evidence of practical drift; the violation signal follows "
            "effect size, not the p-values."
        )
    if mmd.get("mmd2", 0) < 0:
        notes.append("Negative MMD² is expected from the unbiased linear estimator when the "
                     "two samples are close; reported unclipped.")

    return MonitorResult(
        monitor="a1_distribution",
        assumption="A1",
        evidence_class="OBSERVED",
        raw={"max_psi": max_psi, "worst_feature": worst,
             "n_features_above_psi_threshold": int(n_material),
             "n_features_moderate": int(n_moderate),
             "n_features_significant_fdr": int(n_significant),
             "n_features_tested": len(names), "mmd": mmd},
        threshold={"psi": cfg["psi_threshold"], "psi_minor": cfg["psi_minor_threshold"],
                   "alpha_fdr": cfg["ks_alpha"]},
        violation=violation,
        triggered=max_psi >= cfg["psi_threshold"],
        evidence={"per_feature": per_feature,
                  "n_reference": len(reference), "n_window": len(window)},
        notes=notes,
    )
