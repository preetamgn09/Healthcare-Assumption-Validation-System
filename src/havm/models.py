"""Prediction-model baselines and the freeze step.

The prediction model is the OBJECT BEING MONITORED, not the contribution. Three
candidates only, in increasing capacity, and no deep learning (BRIEF §19). Once selected
on source-domain validation, the model is frozen and never retrained during the primary
monitoring experiment (BRIEF §49).
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


class PrevalenceBaseline(BaseEstimator, ClassifierMixin):
    """Predicts the training prevalence for every row. The floor any model must beat."""

    def fit(self, X, y):
        self.prevalence_ = float(np.mean(y))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        p = np.full(len(X), self.prevalence_)
        return np.column_stack([1 - p, p])


def build_model(name: str, numeric: list[str], categorical: list[str], seed: int) -> Pipeline:
    if name == "prevalence":
        return Pipeline([("model", PrevalenceBaseline())])

    if name == "logistic_regression":
        pre = ColumnTransformer([
            ("num", StandardScaler(), numeric),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), categorical),
        ])
        return Pipeline([
            ("pre", pre),
            ("model", LogisticRegression(max_iter=2000, C=1.0, random_state=seed)),
        ])

    if name == "gradient_boosting":
        pre = ColumnTransformer([
            ("num", "passthrough", numeric),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), categorical),
        ])
        cat_mask = [False] * len(numeric) + [True] * len(categorical)
        return Pipeline([
            ("pre", pre),
            ("model", HistGradientBoostingClassifier(
                categorical_features=cat_mask,
                learning_rate=0.05, max_iter=300, early_stopping=True,
                validation_fraction=0.15, random_state=seed,
            )),
        ])

    raise ValueError(f"Unknown model: {name}")


def fit_predict(name, train, validation, numeric, categorical, label, seed):
    model = build_model(name, numeric, categorical, seed)
    model.fit(train[numeric + categorical], train[label])
    return model, model.predict_proba(validation[numeric + categorical])[:, 1]
