"""Replay engine.

One implementation serves historical replay and simulated streaming (BRIEF §31): both are
a sequence of (window_id, frame, metadata) tuples. What differs is only how the frame is
partitioned, which is a config choice.

Strategies:
  random_partition   K equal windows drawn without replacement. Used for D2, which has NO
                     TIME AXIS. This is explicitly not a time series: it exists to exercise
                     the state machine and to test AHS stability on a homogeneous stream,
                     and no detection-delay or trajectory claim may be made from it.
  temporal           windows cut on a datetime column at a stated frequency. For D1
                     (BRFSS) at Gate 6. Not usable on D2 — there is no date column, and
                     encounter_id ordering is an unverifiable proxy this project refuses.
  sequence           an explicitly constructed list of frames, used for injected
                     severity ramps where the ordering is declared, not discovered.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd


def random_partition(df: pd.DataFrame, n_windows: int, seed: int) -> Iterator[tuple]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(df))
    for i, chunk in enumerate(np.array_split(order, n_windows)):
        yield (
            f"W{i:03d}",
            df.iloc[chunk].copy(),
            {"strategy": "random_partition", "index": i, "n": len(chunk),
             "evidence_class": "OBSERVED",
             "caveat": "arbitrary partition of a dataset with no time axis; not a time series"},
        )


def temporal(df: pd.DataFrame, date_column: str, freq: str) -> Iterator[tuple]:
    if date_column not in df.columns:
        raise ValueError(
            f"{date_column} not present. D2 has no date column and encounter_id ordering "
            "is not an acceptable proxy — use random_partition, or D1 for temporal replay."
        )
    for i, (period, block) in enumerate(df.groupby(pd.Grouper(key=date_column, freq=freq))):
        if len(block):
            yield (
                f"{period:%Y-%m}",
                block.copy(),
                {"strategy": "temporal", "period": str(period), "index": i,
                 "n": len(block), "evidence_class": "OBSERVED"},
            )


def sequence(frames: list[tuple]) -> Iterator[tuple]:
    for i, (name, frame, meta) in enumerate(frames):
        yield (name, frame, {"strategy": "sequence", "index": i, "n": len(frame), **meta})


def build(strategy: str, **kwargs) -> Iterator[tuple]:
    return {"random_partition": random_partition, "temporal": temporal, "sequence": sequence}[strategy](**kwargs)
