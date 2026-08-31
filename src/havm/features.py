"""Feature construction for D2.

Two derived columns, both deliberate:

  diag_1_group             ICD-9 primary diagnosis collapsed to the nine clinical groups
                           used by Strack et al. (2014) for this dataset. Keeps the ICD-9
                           vocabulary visible to structural monitoring instead of
                           one-hot-exploding ~700 raw codes.
  medical_specialty_grouped  Long tail collapsed to the most frequent specialties observed
                           IN TRAINING; everything else becomes "Other". The retained set is
                           fitted on training data only and stored in the registry, so a new
                           specialty appearing at deployment is a detectable A3 event rather
                           than a silent remap.
"""
from __future__ import annotations

import pandas as pd

# Strack et al. (2014), Table 2 groupings.
_ICD9_RANGES = [
    ("Circulatory", [(390, 459), (785, 785)]),
    ("Respiratory", [(460, 519), (786, 786)]),
    ("Digestive", [(520, 579), (787, 787)]),
    ("Injury", [(800, 999)]),
    ("Musculoskeletal", [(710, 739)]),
    ("Genitourinary", [(580, 629), (788, 788)]),
    ("Neoplasms", [(140, 239)]),
]


def group_icd9(code: object) -> str:
    """Map a raw ICD-9 code string to a clinical group. Unmappable codes are labelled, not dropped."""
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return "Missing"
    text = str(code).strip()
    if text in {"", "Unknown", "?", "nan"}:
        return "Missing"
    if text.startswith(("V", "v")):
        return "Other_V"
    if text.startswith(("E", "e")):
        return "Other_E"
    try:
        value = float(text)
    except ValueError:
        return "Unmappable"
    if 250 <= value < 251:
        return "Diabetes"
    whole = int(value)
    for name, ranges in _ICD9_RANGES:
        for low, high in ranges:
            if low <= whole <= high:
                return name
    return "Other"


def fit_specialty_vocabulary(train: pd.DataFrame, top_n: int = 12) -> list[str]:
    return train["medical_specialty"].value_counts().head(top_n).index.tolist()


def build_feature_frame(df: pd.DataFrame, cfg: dict, specialty_vocab: list[str] | None = None) -> pd.DataFrame:
    df = df.copy()
    df["diag_1_group"] = df["diag_1"].map(group_icd9)
    if specialty_vocab is None:
        specialty_vocab = fit_specialty_vocabulary(df)
    df["medical_specialty_grouped"] = df["medical_specialty"].where(
        df["medical_specialty"].isin(specialty_vocab), "Other"
    )
    # Admin codes are identifiers, not magnitudes — treat as categories.
    for col in ("admission_type_id", "discharge_disposition_id"):
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


def feature_columns(cfg: dict) -> list[str]:
    return list(cfg["features"]["numeric"]) + list(cfg["features"]["categorical"])
