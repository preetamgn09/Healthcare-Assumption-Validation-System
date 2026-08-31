"""Out-of-distribution detection for tabular EHR data.

This module exists to answer RQ3, which is the one research question in this project with a
strong published prior: Ulmer et al. tested a range of uncertainty-estimation techniques on
mixed-type tabular EHR data with clinically realistic OOD patient groups, and found that
almost all of them failed. That is the only direct clinical evidence in the reviewed corpus
on our modality, and it is a negative result. This module is a replication attempt in a new
direction — shift/OOD detectors rather than uncertainty methods.

Six detectors, chosen to span the families the corpus names:

  mahalanobis     distance in a shrinkage-regularised covariance of the encoded features
  knn             mean distance to the k nearest reference points
  isolation_forest  density/partition-based outlier score
  predictive_entropy   uncertainty of the frozen model  (Ulmer's family)
  max_softmax     1 - max class probability, the classic baseline  (Ulmer's family)
  energy          -logsumexp(logits)

A note on the energy score, because the brief asks for it specifically. Energy is defined
over classifier logits. The frozen model is a gradient-boosted tree, whose raw scores are
log-odds rather than a logit vector, so applying the paper's energy formulation to it would
be a category error dressed up as an implementation. It is therefore computed on a logistic
regression fitted to the same features — a genuine two-logit linear classifier — and that
substitution is reported wherever the number appears. This is what BRIEF §7 asks for:
implement the energy method only if it is mathematically meaningful for the chosen model.
"""
from __future__ import annotations

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from havm.monitors.base import MonitorResult, normalise


class TabularOOD:
    """Fits every detector on the reference (training) data. Fit once, score many."""

    def __init__(self, numeric: list[str], categorical: list[str], seed: int = 20260819,
                 knn_k: int = 10, max_reference: int = 10000):
        self.numeric, self.categorical = numeric, categorical
        self.seed, self.knn_k, self.max_reference = seed, knn_k, max_reference

    def _encode(self, df, fit: bool = False):
        num = df[self.numeric].to_numpy(dtype=float)
        cat = df[self.categorical].astype(str)
        if fit:
            self.scaler_ = StandardScaler().fit(num)
            self.ohe_ = OneHotEncoder(handle_unknown="ignore", min_frequency=50,
                                      sparse_output=False).fit(cat)
        return np.hstack([self.scaler_.transform(num), self.ohe_.transform(cat)])

    def fit(self, reference, y_reference):
        rng = np.random.default_rng(self.seed)
        X = self._encode(reference, fit=True)
        idx = rng.choice(len(X), min(len(X), self.max_reference), replace=False)
        Xs = X[idx]

        self.cov_ = LedoitWolf().fit(Xs)          # shrinkage: the one-hot block is singular
        self.knn_ = NearestNeighbors(n_neighbors=self.knn_k).fit(Xs)
        self.iforest_ = IsolationForest(n_estimators=200, random_state=self.seed).fit(Xs)
        self.lr_ = LogisticRegression(max_iter=2000).fit(X, np.asarray(y_reference))
        return self

    def scores(self, window, model_probs) -> dict[str, np.ndarray]:
        X = self._encode(window)
        p = np.clip(np.asarray(model_probs, dtype=float), 1e-9, 1 - 1e-9)

        dist, _ = self.knn_.kneighbors(X)
        logits = np.column_stack([np.zeros(len(X)), self.lr_.decision_function(X)])

        return {
            "mahalanobis": self.cov_.mahalanobis(X),
            "knn": dist.mean(axis=1),
            "isolation_forest": -self.iforest_.score_samples(X),
            "predictive_entropy": -(p * np.log(p) + (1 - p) * np.log(1 - p)),
            "max_softmax": 1.0 - np.maximum(p, 1 - p),
            "energy": -np.logaddexp(logits[:, 0], logits[:, 1]),
        }


def ood_monitor(scores: np.ndarray, reference_scores: np.ndarray, registry: dict,
                detector: str) -> MonitorResult:
    """Window-level OOD exposure: the fraction of rows beyond a reference quantile.

    The threshold is a quantile of the REFERENCE score distribution, not an absolute value,
    because OOD scores have no natural units and no cross-detector comparability.
    """
    cfg = registry["monitor_config"]["monitors"]["ood"]
    norm = registry["monitor_config"]["normalisation"]["method"]
    cut = float(np.quantile(reference_scores, cfg["reference_quantile"]))
    rate = float(np.mean(np.asarray(scores) > cut))
    expected = 1.0 - cfg["reference_quantile"]
    excess = max(rate - expected, 0.0)

    return MonitorResult(
        monitor="ood",
        assumption="ood",
        evidence_class="OBSERVED",
        raw={"flagged_rate": rate, "expected_rate": expected, "excess": excess,
             "detector": detector, "cutoff": cut},
        threshold={"excess_rate": cfg["excess_rate_threshold"],
                   "reference_quantile": cfg["reference_quantile"]},
        violation=normalise(excess, cfg["excess_rate_threshold"], norm),
        triggered=excess >= cfg["excess_rate_threshold"],
        evidence={},
        notes=[f"Detector: {detector}. Ulmer et al. found uncertainty-based methods "
               "unreliable as OOD detectors on tabular EHR data; the detector choice is "
               "therefore a research variable here, not a settled default."],
    )
