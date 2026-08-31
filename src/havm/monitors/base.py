"""Common monitor interface (BRIEF §55).

Every monitor implements:

    monitor(window, reference, model, registry) -> MonitorResult

and returns the same structure regardless of what it measures. That uniformity is what
lets aggregation, triage and audit be written once instead of per-monitor, and it is what
makes an alert reconstructible from the audit log alone.

A MonitorResult separates four things the literature routinely collapses:

    raw          what was measured (units of the metric)
    threshold    the declared bound it was compared against (POLICY)
    violation    the normalised signal in [0,1] that feeds the AHS
    evidence     everything needed to explain the number to a human

`violation` is deliberately NOT computed from `raw` inside each monitor by an ad-hoc rule:
normalisation is a single declared function, applied identically everywhere, so that the
Gate 6 sensitivity experiment can swap it in one place.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MonitorResult:
    monitor: str
    assumption: str                 # A1 | A2 | A3 | A4 | calibration | ood | fairness
    evidence_class: str             # OBSERVED | INJECTED | SIMULATED
    raw: dict[str, Any]
    threshold: dict[str, Any]
    violation: float                # normalised, [0, 1]
    triggered: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not 0.0 <= self.violation <= 1.0:
            raise ValueError(f"{self.monitor}: violation {self.violation} outside [0,1]")

    def to_dict(self) -> dict:
        return asdict(self)


def normalise(value: float, threshold: float, method: str = "threshold_relative") -> float:
    """Map a raw metric onto [0,1]. The choice of function here is a research variable.

    threshold_relative  v = clip(value / threshold, 0, 1)  — 1.0 means "at or beyond the
                        declared bound", so the signal saturates exactly where the policy
                        says the assumption has failed. Saturation is a real limitation
                        (see implementation_hypotheses.md H3) and is measured, not hidden.
    linear_clip         v = clip(value, 0, 1) — for metrics already on a [0,1] scale.
    soft_exponential    v = 1 - exp(-value / threshold) — approaches 1 asymptotically and
                        never reaches it, so severity beyond the bound stays ordered
                        instead of collapsing. Added after EXP003 showed threshold_relative
                        saturating; whether it helps is RQ5b, not an assumption.
    """
    if value is None:
        return 0.0
    value = max(float(value), 0.0)
    if method == "linear_clip":
        return min(value, 1.0)
    if method == "threshold_relative":
        if threshold in (None, 0):
            return 0.0
        return min(value / float(threshold), 1.0)
    if method == "soft_exponential":
        if threshold in (None, 0):
            return 0.0
        import math
        return 1.0 - math.exp(-value / float(threshold))
    raise ValueError(f"Unknown normalisation method: {method}")


def benjamini_hochberg(pvalues: list[float], alpha: float) -> list[bool]:
    """Return per-test rejection flags under BH-FDR control.

    Without this, running one test per feature per window manufactures false alarms in
    proportion to the feature count — the alert volume would measure the schema width
    rather than the data. No reviewed paper addresses this; it is added here deliberately.
    """
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    rejected = [False] * n
    max_k = -1
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= alpha * rank / n:
            max_k = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= max_k:
            rejected[idx] = True
    return rejected
