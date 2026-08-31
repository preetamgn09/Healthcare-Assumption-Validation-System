"""Governance state machine and audit trail.

The state machine produces POLICY DECISIONS ONLY. Nothing here performs an automated
clinical action; the most severe state is a recommendation to suspend automated prediction,
recorded for a human to act on. This is a SIMULATION of a governance policy (BRIEF §32) and
carries no evidence about how a hospital would actually behave.

Two variants run on identical monitor output so their difference can be counted (H10/RQ9):

  separated  detection -> harm assessment -> governance   (the proposed design)
  collapsed  detection -> governance                      (the comparator)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from havm.utils import environment_record, sha256_obj, write_json

STATES = ["NORMAL", "MONITOR", "GOVERNANCE_REVIEW", "HUMAN_REVIEW_REQUIRED",
          "ABSTENTION_RECOMMENDED", "AUTOMATED_PREDICTION_SUSPENSION"]
SEVERITY = {s: i for i, s in enumerate(STATES)}


@dataclass
class GovernanceEngine:
    registry: dict
    variant: str = "separated"
    state: str = "NORMAL"
    consecutive: int = 0
    pending: str = "NORMAL"
    history: list = field(default_factory=list)

    @property
    def _cfg(self):
        return self.registry["monitor_config"]["governance"]

    def _proposed_state(self, ahs: float, harm: dict | None) -> tuple[str, str]:
        bands = self._cfg["bands"]

        if self.variant == "collapsed":
            # No harm assessment: AHS bands drive action directly.
            if ahs < bands["suspension"]:
                return "AUTOMATED_PREDICTION_SUSPENSION", "AHS below suspension band"
            if ahs < bands["review"]:
                return "GOVERNANCE_REVIEW", "AHS below review band"
            return "NORMAL", "AHS within band"

        level = harm["harm_level"]
        if level == "NONE":
            return ("MONITOR" if harm["input_monitors_triggered"] else "NORMAL",
                    "detected change without measured harm" if harm["input_monitors_triggered"]
                    else "no monitor beyond bound")
        if level == "POTENTIAL":
            return ("GOVERNANCE_REVIEW" if ahs < bands["review"] else "MONITOR",
                    "corroborated input change; AHS below review band" if ahs < bands["review"]
                    else "corroborated input change, AHS still within band")
        # MEASURED
        if ahs < bands["suspension"]:
            return "ABSTENTION_RECOMMENDED", "measured behaviour change with AHS below suspension band"
        return "HUMAN_REVIEW_REQUIRED", "measured behaviour change"

    def step(self, window_id, ahs: float, harm: dict | None) -> dict:
        proposed, reason = self._proposed_state(ahs, harm)
        persistence = self._cfg["persistence_windows"]

        if proposed == self.pending:
            self.consecutive += 1
        else:
            self.pending, self.consecutive = proposed, 1

        escalating = SEVERITY[proposed] > SEVERITY[self.state]
        # Escalation requires persistence; de-escalation is immediate, because holding a
        # model under restriction after the condition has cleared is its own harm.
        if escalating and self.consecutive < persistence:
            applied, applied_reason = self.state, (
                f"{proposed} proposed but held: {self.consecutive}/{persistence} windows")
        else:
            applied, applied_reason = proposed, reason

        transition = {
            "window_id": window_id, "variant": self.variant,
            "from_state": self.state, "to_state": applied,
            "proposed_state": proposed, "reason": applied_reason,
            "ahs": ahs, "harm_level": harm["harm_level"] if harm else None,
            "escalation": SEVERITY[applied] > SEVERITY[self.state],
            "de_escalation": SEVERITY[applied] < SEVERITY[self.state],
        }
        self.state = applied
        self.history.append(transition)
        return {"state": applied, **transition}

    def summary(self) -> dict:
        occupancy = {s: 0 for s in STATES}
        for t in self.history:
            occupancy[t["to_state"]] += 1
        return {
            "variant": self.variant,
            "n_windows": len(self.history),
            "escalations": sum(t["escalation"] for t in self.history),
            "de_escalations": sum(t["de_escalation"] for t in self.history),
            "state_occupancy": occupancy,
            "reached_suspension": any(
                t["to_state"] == "AUTOMATED_PREDICTION_SUSPENSION" for t in self.history),
            "final_state": self.state,
        }


class AuditTrail:
    """Append-only record. Every field BRIEF §15 requires, so that an alert can be
    reconstructed from the log alone without re-running anything."""

    def __init__(self, registry: dict):
        self.registry = registry
        self.records: list[dict] = []

    def record(self, *, window_id, window_meta, results, ahs_result, harm, governance, packet):
        self.records.append({
            "timestamp": environment_record()["timestamp_utc"],
            "window_id": window_id,
            "window": window_meta,
            "model_version": self.registry["model"]["model_version"],
            "model_id": self.registry["model"]["model_id"],
            "dataset_version": self.registry["dataset"]["version"],
            "registry_version": self.registry["registry_version"],
            "registry_hash": self.registry.get("registry_hash"),
            "monitor_config_hash": sha256_obj(self.registry["monitor_config"]),
            "monitors": [{
                "monitor": r["monitor"], "assumption": r["assumption"],
                "evidence_class": r["evidence_class"], "raw": r["raw"],
                "threshold": r["threshold"], "violation": r["violation"],
                "triggered": r["triggered"],
            } for r in results],
            "ahs": ahs_result["ahs"],
            "ahs_components": {k: v["contribution_renormalised"]
                               for k, v in ahs_result["components"].items()},
            "harm_assessment": harm,
            "governance": governance,
            "alert_packet": packet,
            "human_decision": None,      # populated only by a real reviewer
            "rollback_information": {"frozen_model_artifact": self.registry["model"]["artifact"],
                                     "artifact_sha256": self.registry["model"]["artifact_sha256"]},
        })

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(path, "w") as fh:
            for rec in self.records:
                fh.write(json.dumps(rec, default=str) + "\n")
        return path
