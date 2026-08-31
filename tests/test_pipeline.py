"""Pipeline correctness tests. These guard the failure modes that would silently
invalidate every downstream monitoring result: leakage, non-determinism, and a schema
contract that cannot detect the violations it exists to detect."""
import pandas as pd
import pytest

from havm.features import group_icd9
from havm.schema import fit_schema, validate


# ---------------------------------------------------------------- feature mapping
@pytest.mark.parametrize("code,expected", [
    ("250.83", "Diabetes"), ("250", "Diabetes"),
    ("428", "Circulatory"), ("410.1", "Circulatory"), ("785", "Circulatory"),
    ("486", "Respiratory"), ("574", "Digestive"), ("820", "Injury"),
    ("715", "Musculoskeletal"), ("585", "Genitourinary"), ("197", "Neoplasms"),
    ("V57", "Other_V"), ("E909", "Other_E"), ("Unknown", "Missing"), ("042", "Other"),
])
def test_icd9_grouping(code, expected):
    assert group_icd9(code) == expected


# ---------------------------------------------------------------- schema contract
def _toy_cfg():
    return {"features": {"numeric": ["n"], "categorical": ["c"]}}


def test_schema_validates_its_own_training_data():
    df = pd.DataFrame({"n": [1, 2, 3], "c": ["a", "b", "a"]})
    assert validate(df, fit_schema(df, _toy_cfg())) == []


def test_schema_detects_unseen_category():
    train = pd.DataFrame({"n": [1, 2], "c": ["a", "b"]})
    later = pd.DataFrame({"n": [1, 2], "c": ["a", "ZZZ"]})
    v = validate(later, fit_schema(train, _toy_cfg()))
    assert [x["type"] for x in v] == ["unseen_category"]
    assert v[0]["values"] == ["ZZZ"]


def test_schema_detects_missing_column():
    train = pd.DataFrame({"n": [1, 2], "c": ["a", "b"]})
    v = validate(pd.DataFrame({"n": [1, 2]}), fit_schema(train, _toy_cfg()))
    assert [x["type"] for x in v] == ["missing_column"]


def test_schema_detects_out_of_range():
    train = pd.DataFrame({"n": [1, 2], "c": ["a", "b"]})
    v = validate(pd.DataFrame({"n": [999], "c": ["a"]}), fit_schema(train, _toy_cfg()))
    assert v[0]["type"] == "out_of_range" and v[0]["above_max"] == 1


# ---------------------------------------------------------------- real-data guards
def test_train_and_validation_are_patient_disjoint(splits, cfg):
    g = cfg["split"]["group_column"]
    assert not (set(splits.train[g]) & set(splits.validation[g]))


def test_label_matches_its_definition(splits, cfg):
    label, src = cfg["label"]["name"], cfg["label"]["source_column"]
    for frame in (splits.train, splits.validation):
        expected = frame[src].isin(cfg["label"]["positive_values"]).astype(int)
        assert (frame[label] == expected).all()


def test_excluded_discharges_are_absent(splits, cfg):
    for frame in (splits.train, splits.validation, splits.target_sealed):
        assert not frame["discharge_disposition_id"].isin(
            cfg["cohort"]["exclude_discharge_disposition_ids"]
        ).any()


def test_domain_column_is_not_a_model_feature(cfg):
    from havm.features import feature_columns

    assert cfg["domain"]["column"] not in feature_columns(cfg), (
        "the column defining the shift must never be a model input — it would let the "
        "model learn the domain instead of the outcome"
    )


def test_domains_are_disjoint_and_correctly_assigned(splits, cfg):
    col, target_values = cfg["domain"]["column"], cfg["domain"]["target_values"]
    assert splits.target_sealed[col].isin(target_values).all()
    for frame in (splits.train, splits.validation):
        assert not frame[col].isin(target_values).any()


def test_split_is_deterministic(cfg, splits):
    from havm.datasets.d2 import build_splits

    again = build_splits(cfg)
    assert splits.train["encounter_id"].tolist() == again.train["encounter_id"].tolist()
    assert splits.target_sealed["encounter_id"].tolist() == again.target_sealed["encounter_id"].tolist()


def test_none_is_preserved_as_a_category_not_a_missing_value(splits):
    """Regression test: pandas' default NA list swallows the literal 'None', which in this
    dataset means 'test not performed'. Losing it would erase a real A3 signal."""
    assert "None" in set(splits.train["A1Cresult"].unique())
    assert splits.train["A1Cresult"].isna().sum() == 0
