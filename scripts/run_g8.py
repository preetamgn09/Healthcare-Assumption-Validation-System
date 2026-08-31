"""EXP009–EXP010 — Gate 8 (measurement).

    python scripts/run_g8.py

EXP009  RQ7 — scalability. Measured, not asserted (BRIEF §30). Monitoring cost against
        dataset fraction and against window size, with wall-clock, peak memory and
        throughput recorded per configuration on stated hardware.

EXP010  AHS stability, repeated. EXP003 Finding 1 rested on ten windows and one seed. It
        is the finding that currently blocks every threshold claim, so it gets the
        repetition it needs: 30 independent partitions of the deployment domain, plus the
        same at several window counts.
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm import replay
from havm.aggregation import compute_ahs
from havm.datasets.d2 import build_splits
from havm.monitors.distribution import monitor as a1_monitor
from havm.monitors.ood import TabularOOD, ood_monitor
from havm.monitors.relational import operational_monitor, relational_monitor, simulate_batch
from havm.monitors.structural import calibration_monitor, fairness_monitor, structural_monitor
from havm.utils import environment_record, load_config, sha256_obj, write_json


def peak_memory_mb() -> float:
    """Peak RSS of this process. On Linux ru_maxrss is in kilobytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def monitor_set(window, reference, model, registry, features, label, ood=None, ref_scores=None):
    probs = model.predict_proba(window[features])[:, 1]
    results = [
        a1_monitor(window, reference, registry).to_dict(),
        structural_monitor(window, registry).to_dict(),
        calibration_monitor(window[label].to_numpy(), probs, registry).to_dict(),
        fairness_monitor(window, probs, registry).to_dict(),
    ]
    if ood is not None:
        det = registry["monitor_config"]["monitors"]["ood"]["detector"]
        scores = ood.scores(window, probs)[det]
        results.append(ood_monitor(scores, ref_scores, registry, det).to_dict())
        results.append(operational_monitor(simulate_batch("w", seed=0), registry).to_dict())
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--monitors", default="configs/monitors.yaml")
    ap.add_argument("--registry", default="results/registry/EXP008_registry.json")
    ap.add_argument("--model", default="results/models/EXP001_frozen_model.joblib")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    registry = json.loads(Path(args.registry).read_text())
    registry["monitor_config"] = load_config(args.monitors)
    registry["monitor_config"]["monitors"]["fairness"]["null_band"]["enabled"] = False
    model = joblib.load(args.model)
    out = Path(args.outdir)

    numeric = registry["model"]["features"]["numeric"]
    categorical = registry["model"]["features"]["categorical"]
    features = numeric + categorical
    label = cfg["label"]["name"]

    t0 = time.perf_counter()
    splits = build_splits(cfg)
    pipeline_seconds = time.perf_counter() - t0
    reference, deployment = splits.train, splits.target_sealed
    print(f"[EXP009] full pipeline (load, cohort, split, features): {pipeline_seconds:.1f}s")

    hardware = {"platform": platform.platform(), "processor": platform.processor() or "unknown",
                "cpu_count": __import__("os").cpu_count()}

    # ------------------------------------------------------------------ EXP009a
    print("\n[EXP009a] monitoring cost vs window size (four monitors, no OOD)")
    by_size = {}
    for n in (1000, 2500, 5000, 10000, 25000, 55848):
        win = deployment.sample(n=min(n, len(deployment)), random_state=7)
        m0, t1 = peak_memory_mb(), time.perf_counter()
        monitor_set(win, reference, model, registry, features, label)
        elapsed = time.perf_counter() - t1
        by_size[n] = {"n": len(win), "seconds": elapsed, "rows_per_second": len(win) / elapsed,
                      "peak_rss_mb": peak_memory_mb(), "rss_delta_mb": peak_memory_mb() - m0}
        print(f"   n={len(win):>6,}  {elapsed:6.2f}s  {len(win)/elapsed:>9,.0f} rows/s  "
              f"peak RSS {peak_memory_mb():.0f} MB")

    # ------------------------------------------------------------------ EXP009b
    print("\n[EXP009b] cost vs reference size (the two-sample comparison scales with both)")
    by_reference = {}
    win = deployment.sample(n=5000, random_state=7)
    for frac in (0.10, 0.25, 0.50, 0.75, 1.00):
        ref = reference.sample(frac=frac, random_state=7)
        t1 = time.perf_counter()
        monitor_set(win, ref, model, registry, features, label)
        elapsed = time.perf_counter() - t1
        by_reference[frac] = {"n_reference": len(ref), "seconds": elapsed}
        print(f"   reference {frac:>5.0%} ({len(ref):>6,} rows)  {elapsed:6.2f}s")

    # ------------------------------------------------------------------ EXP009c
    print("\n[EXP009c] full seven-monitor cost, including OOD detector fit")
    t1 = time.perf_counter()
    ood = TabularOOD(numeric, categorical).fit(reference, reference[label])
    fit_seconds = time.perf_counter() - t1
    ref_scores = ood.scores(reference, model.predict_proba(reference[features])[:, 1])[
        registry["monitor_config"]["monitors"]["ood"]["detector"]]
    t1 = time.perf_counter()
    monitor_set(win, reference, model, registry, features, label, ood=ood, ref_scores=ref_scores)
    seven_seconds = time.perf_counter() - t1
    print(f"   OOD detector fit (one-off): {fit_seconds:.1f}s")
    print(f"   seven monitors on n=5,000:  {seven_seconds:.2f}s  "
          f"(four monitors: {by_size[5000]['seconds']:.2f}s)")

    # ------------------------------------------------------------------ EXP010
    print("\n[EXP010] AHS stability — 30 independent partitions of the deployment domain")
    stability = {}
    for n_windows in (5, 10, 20):
        scores = []
        for seed in range(30):
            wid, frame, _ = next(iter(replay.build("random_partition", df=deployment,
                                                   n_windows=n_windows, seed=9000 + seed)))
            res = monitor_set(frame, reference, model, registry, features, label)
            scores.append(compute_ahs(res, registry)["ahs"])
        stability[n_windows] = {
            "window_rows": int(len(deployment) / n_windows), "n_repeats": len(scores),
            "mean": float(np.mean(scores)), "sd": float(np.std(scores)),
            "range": [float(min(scores)), float(max(scores))],
            "p05_p95": [float(np.percentile(scores, 5)), float(np.percentile(scores, 95))],
            "scores": [float(s) for s in scores]}
        s = stability[n_windows]
        print(f"   {n_windows:>2} windows (n≈{s['window_rows']:,}): mean {s['mean']:.3f}  "
              f"sd {s['sd']:.4f}  range [{s['range'][0]:.3f}, {s['range'][1]:.3f}]  "
              f"5–95% span {s['p05_p95'][1] - s['p05_p95'][0]:.3f}")

    bands = registry["monitor_config"]["governance"]["bands"]
    band_width = bands["review"] - bands["suspension"]
    worst = max(stability.values(), key=lambda s: s["p05_p95"][1] - s["p05_p95"][0])
    print(f"\n   governance band width (review - suspension) = {band_width:.2f}")
    print(f"   widest 5–95% AHS span on unchanged data      = "
          f"{worst['p05_p95'][1] - worst['p05_p95'][0]:.3f}")

    write_json({
        "experiment_ids": ["EXP009", "EXP010"],
        "environment": environment_record(), "hardware": hardware,
        "config_hash": sha256_obj(cfg),
        "exp009_scalability": {
            "pipeline_seconds": pipeline_seconds,
            "by_window_size": by_size, "by_reference_fraction": by_reference,
            "ood_fit_seconds": fit_seconds, "seven_monitor_seconds_n5000": seven_seconds,
            "four_monitor_seconds_n5000": by_size[5000]["seconds"],
        },
        "exp010_ahs_stability": {
            "by_window_count": stability,
            "governance_band_width": band_width,
            "widest_p05_p95_span": worst["p05_p95"][1] - worst["p05_p95"][0],
        },
    }, out / "metrics" / "EXP009-010_scalability_stability.json")
    print(f"\n[G8] written to {out}/metrics/EXP009-010_scalability_stability.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
