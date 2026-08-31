"""D2 — Diabetes 130-US Hospitals loader.

Responsibilities, in order:
  verify the raw file  ->  build the cohort  ->  define the label
  ->  split into source/target domains  ->  split source by PATIENT into train/validation

The target (deployment) domain is returned but is SEALED at Gate 3: nothing in model
selection may touch it. run_g3 records its hash so that can be demonstrated later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from havm.utils import sha256_file


@dataclass
class Splits:
    train: pd.DataFrame
    validation: pd.DataFrame
    target_sealed: pd.DataFrame
    provenance: dict = field(default_factory=dict)


def verify_raw(cfg: dict) -> dict:
    """Check the raw file against the declared checksum and shape before anything reads it."""
    d = cfg["dataset"]
    actual = sha256_file(d["raw_file"])
    record = {
        "file": d["raw_file"],
        "sha256_expected": d["expected_sha256"],
        "sha256_actual": actual,
        "checksum_match": actual == d["expected_sha256"],
        "provenance_status": d.get("provenance_status", "UNKNOWN"),
    }
    if not record["checksum_match"]:
        raise ValueError(
            f"Raw file checksum mismatch for {d['raw_file']}.\n"
            f"  expected {d['expected_sha256']}\n  actual   {actual}\n"
            "Refusing to proceed: an unversioned dataset makes every downstream result unreproducible."
        )
    return record


def load_raw(cfg: dict) -> pd.DataFrame:
    d = cfg["dataset"]
    # keep_default_na=False is essential, not stylistic. In this file the literal string
    # "None" in max_glu_serum / A1Cresult means "the test was not performed" — real
    # information about clinical practice. Pandas' default NA list would silently convert
    # it to a missing value, collapsing "not tested" and "not recorded" into one thing and
    # destroying exactly the structural signal A3 monitoring exists to observe.
    df = pd.read_csv(
        d["raw_file"],
        dtype={"diag_1": str, "diag_2": str, "diag_3": str},
        keep_default_na=False,
        na_values=[""],
    )
    if df.shape[0] != d["expected_rows"] or df.shape[1] != d["expected_cols"]:
        raise ValueError(
            f"Shape mismatch: got {df.shape}, expected "
            f"({d['expected_rows']}, {d['expected_cols']})"
        )
    return df


def build_cohort(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Apply the declared exclusions. Every drop is counted and returned."""
    c = cfg["cohort"]
    log = {"rows_in": len(df)}

    mask_disch = ~df["discharge_disposition_id"].isin(c["exclude_discharge_disposition_ids"])
    log["dropped_discharge_expired_or_hospice"] = int((~mask_disch).sum())
    df = df[mask_disch]

    mask_gender = ~df["gender"].isin(c["exclude_gender_values"])
    log["dropped_invalid_gender"] = int((~mask_gender).sum())
    df = df[mask_gender].copy()

    # Missing markers become an explicit category. They are informative, not noise.
    obj_cols = df.select_dtypes(include=["object", "str"]).columns
    for col in obj_cols:
        df[col] = df[col].replace(c["missing_token"], c["missing_label"])

    log["rows_out"] = len(df)
    return df, log


def add_label(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    lab = cfg["label"]
    df = df.copy()
    df[lab["name"]] = df[lab["source_column"]].isin(lab["positive_values"]).astype(int)
    return df


def split_domains(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dom = cfg["domain"]
    col = dom["column"]
    unknown = df[col].isin(dom["unknown_values"])
    target = df[~unknown & df[col].isin(dom["target_values"])]
    source = df[~unknown & ~df[col].isin(dom["target_values"])]
    log = {
        "source_encounters": len(source),
        "target_encounters": len(target),
        "dropped_unknown_admission_source": int(unknown.sum()),
        "source_prevalence": round(float(source[cfg["label"]["name"]].mean()), 5),
        "target_prevalence_SEALED": None,  # deliberately not computed at Gate 3
    }
    return source.copy(), target.copy(), log


def split_train_validation(source: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Grouped by patient. A patient's encounters never straddle train and validation."""
    s = cfg["split"]
    groups = source[s["group_column"]].drop_duplicates()
    shuffled = groups.sample(frac=1.0, random_state=s["seed"])
    n_val = int(round(len(shuffled) * s["validation_fraction"]))
    val_patients = set(shuffled.iloc[:n_val])

    is_val = source[s["group_column"]].isin(val_patients)
    train, validation = source[~is_val].copy(), source[is_val].copy()

    log = {
        "train_encounters": len(train),
        "validation_encounters": len(validation),
        "train_patients": int(train[s["group_column"]].nunique()),
        "validation_patients": int(validation[s["group_column"]].nunique()),
        "patient_overlap_train_validation": int(
            len(set(train[s["group_column"]]) & set(validation[s["group_column"]]))
        ),
        "train_prevalence": round(float(train[cfg["label"]["name"]].mean()), 5),
        "validation_prevalence": round(float(validation[cfg["label"]["name"]].mean()), 5),
    }
    return train, validation, log


def build_splits(cfg: dict) -> Splits:
    provenance = {"raw": verify_raw(cfg)}
    df = load_raw(cfg)
    df, provenance["cohort"] = build_cohort(df, cfg)
    df = add_label(df, cfg)

    source, target, provenance["domain"] = split_domains(df, cfg)
    train, validation, provenance["split"] = split_train_validation(source, cfg)

    # Feature fitting happens AFTER the split and sees training rows only. Fitting the
    # specialty vocabulary on the full frame would leak deployment-domain information
    # into the frozen model.
    from havm.features import build_feature_frame, fit_specialty_vocabulary

    vocab = fit_specialty_vocabulary(train)
    provenance["features"] = {"medical_specialty_vocabulary": vocab, "fitted_on": "train"}
    train = build_feature_frame(train, cfg, vocab)
    validation = build_feature_frame(validation, cfg, vocab)
    target = build_feature_frame(target, cfg, vocab)

    # Patients appearing in both training and the deployment domain are a real property of
    # the data (people do come back through the ED). Measured and reported, not hidden.
    gcol = cfg["split"]["group_column"]
    overlap = set(train[gcol]) & set(target[gcol])
    provenance["split"]["patient_overlap_train_target"] = len(overlap)
    if cfg["domain"]["exclude_overlapping_patients"]:
        target = target[~target[gcol].isin(overlap)].copy()
        provenance["split"]["target_after_overlap_exclusion"] = len(target)

    return Splits(train=train, validation=validation, target_sealed=target, provenance=provenance)
