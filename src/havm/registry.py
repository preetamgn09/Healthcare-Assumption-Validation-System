"""L2 — the Assumption Registry.

A model card made live and version-controlled. Every monitor built in later stages reads
its configuration from here; nothing downstream may hardcode a threshold or a weight.

Provenance discipline (see research/paper_analysis.md §0): entries are tagged
  PAPER_SPECIFIED  — traceable to a supplied HAVM paper
  BRIEF_SPECIFIED  — from the implementation brief, no paper provenance found
  OBSERVED         — measured from data in this project
  POLICY           — chosen by us, to be varied in sensitivity experiments

At Gate 3 all thresholds and weights are placeholders. They exist so the registry schema
is exercised end to end; none has been evaluated, and no result may rely on their values.
"""
from __future__ import annotations

from pathlib import Path

from havm.utils import environment_record, sha256_obj, write_json

REGISTRY_VERSION = "0.1.0"


def build_registry(*, model_card: dict, schema: dict, provenance: dict, cfg: dict) -> dict:
    reg = {
        "registry_version": REGISTRY_VERSION,
        "gate": "G3",
        "owner": "TO_BE_ASSIGNED",
        "effective_date": environment_record()["timestamp_utc"],
        "model": model_card,
        "dataset": {
            "id": cfg["dataset"]["id"],
            "version": cfg["dataset"]["version"],
            "licence": cfg["dataset"]["licence"],
            "citation": cfg["dataset"]["citation"],
            "provenance": provenance,
        },
        "label_definition": cfg["label"],
        "feature_expectations": schema,
        "subgroups": cfg["subgroups"],
        "monitored_assumptions": {
            "A1_distributional": {"status": "NOT_IMPLEMENTED", "gate": "G4"},
            "A2_relational": {"status": "NOT_IMPLEMENTED", "gate": "G7"},
            "A3_structural": {"status": "SCHEMA_CONTRACT_ONLY", "gate": "G4"},
            "A4_operational": {"status": "NOT_IMPLEMENTED", "gate": "G4", "evidence_class": "SIMULATED"},
            "calibration": {"status": "MEASURED_AT_FREEZE", "gate": "G4"},
            "ood": {"status": "NOT_IMPLEMENTED", "gate": "G7"},
            "fairness": {"status": "MEASURED_AT_FREEZE", "gate": "G4"},
        },
        "thresholds": {
            "_provenance": "BRIEF_SPECIFIED / POLICY — placeholders, never evaluated",
            "psi": 0.20, "ece": 0.05, "fairness_delta": 0.05,
            "ahs_review": 0.75, "ahs_suspension": 0.50,
        },
        "ahs_weights": {
            "_provenance": "POLICY — equal weighting placeholder; a research variable, not a default",
            "a1": 0.2, "a2": 0.2, "a3": 0.1, "a4": 0.1,
            "ood": 0.15, "calibration": 0.15, "fairness": 0.10,
        },
        "governance_policy": {"status": "NOT_IMPLEMENTED", "gate": "G5"},
        "validation_history": [],
    }
    reg["registry_hash"] = sha256_obj({k: v for k, v in reg.items() if k != "registry_hash"})
    return reg


def save(registry: dict, path: str | Path) -> Path:
    return write_json(registry, path)
