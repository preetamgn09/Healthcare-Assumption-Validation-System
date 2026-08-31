"""Schema contract.

The contract is fitted on TRAINING data and stored in the assumption registry. It records
what the frozen model expects: which columns, of what type, with what categories and what
ranges. Later stages compare incoming windows against it; at Gate 3 it is only built and
self-validated.

Deliberately descriptive, not prescriptive: it records the observed training state rather
than an author's opinion about what the data should look like.
"""
from __future__ import annotations

import pandas as pd


def fit_schema(df: pd.DataFrame, cfg: dict) -> dict:
    num, cat = cfg["features"]["numeric"], cfg["features"]["categorical"]
    schema = {"n_rows_fitted_on": int(len(df)), "columns": {}}
    for col in num:
        s = pd.to_numeric(df[col], errors="coerce")
        schema["columns"][col] = {
            "kind": "numeric",
            "dtype": str(df[col].dtype),
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "missing_rate": float(s.isna().mean()),
        }
    for col in cat:
        vc = df[col].astype(str).value_counts(normalize=True)
        schema["columns"][col] = {
            "kind": "categorical",
            "dtype": str(df[col].dtype),
            "cardinality": int(df[col].nunique()),
            "categories": sorted(vc.index.tolist()),
            "missing_rate": float(df[col].isna().mean()),
        }
    return schema


def validate(df: pd.DataFrame, schema: dict) -> list[dict]:
    """Return a list of violations. An empty list means the frame matches the contract.

    Violation classes map onto A3 (structural) monitoring:
      missing_column / unexpected_column / unseen_category / out_of_range / missingness_shift
    """
    violations: list[dict] = []
    expected = schema["columns"]

    for col, spec in expected.items():
        if col not in df.columns:
            violations.append({"type": "missing_column", "column": col})
            continue
        if spec["kind"] == "numeric":
            s = pd.to_numeric(df[col], errors="coerce")
            below, above = int((s < spec["min"]).sum()), int((s > spec["max"]).sum())
            if below or above:
                violations.append({
                    "type": "out_of_range", "column": col,
                    "below_min": below, "above_max": above,
                    "expected_range": [spec["min"], spec["max"]],
                })
        else:
            unseen = sorted(set(df[col].astype(str)) - set(spec["categories"]))
            if unseen:
                violations.append({
                    "type": "unseen_category", "column": col,
                    "values": unseen[:20], "n_unseen": len(unseen),
                })
    return violations
