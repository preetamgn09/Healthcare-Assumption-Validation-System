"""EXP004–EXP006 — Gate 6.

    python scripts/run_g6.py

EXP004  AHS null band vs window size. EXP003 Finding 1 showed AHS moving 0.21 across
        windows drawn from one distribution. Before any threshold curve can be read, that
        noise has to be characterised: how much of it is sample size, and what window size
        would be needed for the governance bands to mean anything?

EXP005  Detection experiment. A window bank of clean and perturbed windows with declared
        ground truth, swept over thresholds, weights and normalisation functions.

EXP006  Baseline ladder and ablation on the same bank: no monitoring, each monitor alone,
        the OR-rule over independent detectors, and AHS.

Ground truth is INJECTED and declared: a window is degraded if and only if a perturbation
was applied to it. Clean windows are resampled from the in-distribution validation set, so
the null really is null — using the deployment domain as "clean" would have meant every
window was already shifted relative to the reference.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from havm.datasets.d2 import build_splits
from havm.monitors.distribution import monitor as a1_monitor
from havm.monitors.structural import calibration_monitor, fairness_monitor, structural_monitor
from havm.sweep import METRIC_SPEC, evaluate, raw_metric, rescore
from havm.utils import environment_record, load_config, sha256_obj, write_json

MONITORS = ["a1_distribution", "a3_structural", "calibration", "fairness"]


def run_monitors(window, reference, model, registry, features, label):
    probs = model.predict_proba(window[features])[:, 1]
    return [r.to_dict() for r in (
        a1_monitor(window, reference, registry),
        structural_monitor(window, registry),
        calibration_monitor(window[label].to_numpy(), probs, registry),
        fairness_monitor(window, probs, registry),
    )]


def perturb(df, severity, seed, n_out):
    rng = np.random.default_rng(seed)
    if severity <= 0:
        return df.sample(n=n_out, replace=True, random_state=seed).copy()
    older = df["age"].isin(["[70-80)", "[80-90)", "[90-100)"])
    weights = np.where(older, 1.0, 1.0 - 0.7 * severity)
    out = df.sample(n=n_out, replace=True, weights=weights, random_state=seed).copy()
    out["number_inpatient"] = out["number_inpatient"] + int(round(3 * severity))
    out["number_emergency"] = out["number_emergency"] + int(round(2 * severity))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--monitors", default="configs/monitors.yaml")
    ap.add_argument("--registry", default="results/registry/EXP003_registry.json")
    ap.add_argument("--model", default="results/models/EXP001_frozen_model.joblib")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    cfg = load_config(args.config)
    registry = json.loads(Path(args.registry).read_text())
    registry["monitor_config"] = load_config(args.monitors)
    # Permutation bands are turned off for the sweep: 200 permutations per window per
    # attribute would dominate the runtime, and no swept policy reads them. The cost is
    # that fairness noise-discounting is unavailable here, so fairness alerts in Gate 6 are
    # threshold-based only — stated rather than quietly dropped.
    registry["monitor_config"]["monitors"]["fairness"]["null_band"]["enabled"] = False
    model = joblib.load(args.model)
    out = Path(args.outdir)

    features = registry["model"]["features"]["numeric"] + registry["model"]["features"]["categorical"]
    label = cfg["label"]["name"]
    splits = build_splits(cfg)
    reference, validation = splits.train, splits.validation
    baselines = {k: v["value"] for k, v in registry.get("freeze_baselines", {}).items()}
    entry_mode = registry["monitor_config"]["ahs"]["entry_mode"]
    default_weights = registry["monitor_config"]["ahs"]["weights"]

    def w_over(names, source):
        sub = {n: source.get(n, 0.0) for n in names}
        total = sum(sub.values())
        return {n: (v / total if total else 0.0) for n, v in sub.items()}

    # ------------------------------------------------------------------ EXP004
    print("[EXP004] AHS null band vs window size (clean windows only)")
    exp004 = {}
    for n in (500, 1000, 2500, 5000, 10000):
        scores = []
        for s in range(20):
            win = validation.sample(n=n, replace=True, random_state=5000 + s)
            res = run_monitors(win, reference, model, registry, features, label)
            scores.append(rescore(res, weights=default_weights, normalisation="threshold_relative",
                                  thresholds={}, baselines=baselines, entry_mode=entry_mode,
                                  ahs_band=0.75)["ahs"])
        exp004[n] = {"n_windows": len(scores), "mean": float(np.mean(scores)),
                     "sd": float(np.std(scores)),
                     "p05_p95": [float(np.percentile(scores, 5)), float(np.percentile(scores, 95))],
                     "range": [float(min(scores)), float(max(scores))],
                     "scores": [float(x) for x in scores]}
        print(f"   n={n:>6,}  mean {np.mean(scores):.3f}  sd {np.std(scores):.4f}  "
              f"range [{min(scores):.3f}, {max(scores):.3f}]")

    # ------------------------------------------------------------------ window bank
    print("\n[EXP005] building window bank (clean + perturbed, n=2,500 each)")
    bank = []
    for s in range(20):
        bank.append(("clean", 0.0, perturb(validation, 0.0, seed=100 + s, n_out=2500)))
    for i, sev in enumerate([0.10, 0.25, 0.50, 0.75, 1.00]):
        for s in range(5):
            bank.append((f"sev{sev}", sev, perturb(validation, sev, seed=200 + 10 * i + s, n_out=2500)))

    records = []
    for i, (kind, sev, frame) in enumerate(bank):
        res = run_monitors(frame, reference, model, registry, features, label)
        records.append({"window_id": f"B{i:03d}", "kind": kind, "severity": sev,
                        "degraded": int(sev > 0),
                        "raw": {r["monitor"]: raw_metric(r) for r in res},
                        "results": res})
    truth = [r["degraded"] for r in records]
    print(f"   {len(records)} windows, {sum(truth)} degraded / {len(truth) - sum(truth)} clean")

    # Null quantiles for the empirical_quantile normalisation, calibrated on the FIRST HALF
    # of the clean windows only. Calibrating on all of them would leak the evaluation set.
    calib = [r for r in records if r["kind"] == "clean"][:10]
    null_quantiles = {m: np.sort([r["raw"][m] for r in calib]) for m in MONITORS}
    eval_idx = [i for i, r in enumerate(records) if not (r["kind"] == "clean" and r in calib)]
    eval_truth = [records[i]["degraded"] for i in eval_idx]
    print(f"   evaluation subset: {len(eval_idx)} windows "
          f"({sum(eval_truth)} degraded), 10 clean windows held out for null calibration")

    decision_store = {}

    def sweep_eval(_tag=None, **kw):
        decisions_ahs, decisions_or = [], []
        for i in eval_idx:
            sc = rescore(records[i]["results"], baselines=baselines, entry_mode=entry_mode,
                         null_quantiles=null_quantiles, **kw)
            decisions_ahs.append(sc["alert_ahs"])
            decisions_or.append(sc["alert_or_rule"])
        if _tag:
            decision_store[_tag] = list(decisions_ahs)
            decision_store.setdefault("independent_or_rule", list(decisions_or))
        return evaluate(decisions_ahs, eval_truth), evaluate(decisions_or, eval_truth)

    # ------------------------------------------------------------------ EXP005
    print("\n[EXP005a] threshold sensitivity (AHS band), default weights, threshold_relative")
    thresholds_sweep = {}
    for band in (0.50, 0.60, 0.70, 0.75, 0.80, 0.90, 0.95):
        m, _ = sweep_eval(weights=default_weights, normalisation="threshold_relative",
                          thresholds={}, ahs_band=band)
        thresholds_sweep[band] = m
        print(f"   band {band:.2f}  precision={m['precision']}  recall={m['recall']}  "
              f"FAR={m['false_alarm_rate']}  alert_rate={m['alert_rate']:.2f}")

    print("\n[EXP005b] normalisation sensitivity (RQ5b), band swept, best F1 reported")
    norm_sweep = {}
    for norm in ("threshold_relative", "soft_exponential", "empirical_quantile"):
        best = None
        for band in np.arange(0.05, 1.0, 0.05):
            m, _ = sweep_eval(weights=default_weights, normalisation=norm,
                              thresholds={}, ahs_band=float(band))
            if m["f1"] is not None and (best is None or m["f1"] > best[1]["f1"]):
                best = (float(band), m)
        norm_sweep[norm] = {"best_band": best[0], **best[1]} if best else None
        if best:
            print(f"   {norm:<20} best band {best[0]:.2f}  F1={best[1]['f1']:.3f}  "
                  f"precision={best[1]['precision']:.3f}  recall={best[1]['recall']:.3f}")

    print("\n[EXP005c] weight sensitivity (RQ5), 200 Dirichlet draws + named configurations")
    rng = np.random.default_rng(20260819)
    named = {
        "equal": {m: 0.25 for m in MONITORS},
        "brief_default": w_over(MONITORS, default_weights),
        "behaviour_weighted": {"a1_distribution": 0.1, "a3_structural": 0.1,
                               "calibration": 0.4, "fairness": 0.4},
        "input_weighted": {"a1_distribution": 0.4, "a3_structural": 0.4,
                           "calibration": 0.1, "fairness": 0.1},
    }
    weight_sweep = {}
    for name, w in named.items():
        m, _ = sweep_eval(weights=w, normalisation="threshold_relative", thresholds={}, ahs_band=0.75)
        weight_sweep[name] = m
        print(f"   {name:<20} precision={m['precision']}  recall={m['recall']}  F1={m['f1']}")

    random_f1 = []
    for _ in range(200):
        w = dict(zip(MONITORS, rng.dirichlet(np.ones(len(MONITORS)))))
        m, _ = sweep_eval(weights=w, normalisation="threshold_relative", thresholds={}, ahs_band=0.75)
        if m["f1"] is not None:
            random_f1.append(m["f1"])
    weight_sweep["random_dirichlet"] = {
        "n": len(random_f1), "f1_mean": float(np.mean(random_f1)), "f1_sd": float(np.std(random_f1)),
        "f1_range": [float(min(random_f1)), float(max(random_f1))]}
    print(f"   random weights (n={len(random_f1)}): F1 mean {np.mean(random_f1):.3f} "
          f"sd {np.std(random_f1):.4f} range [{min(random_f1):.3f}, {max(random_f1):.3f}]")

    # ------------------------------------------------------------------ EXP006
    print("\n[EXP006] baseline ladder and ablation (band 0.75, threshold_relative)")
    ladder = {}
    for name in MONITORS:
        m, _ = sweep_eval(_tag=f"single::{name}", weights={name: 1.0},
                          normalisation="threshold_relative", thresholds={}, ahs_band=0.75)
        ladder[f"single::{name}"] = m
    for pair in (("a1_distribution", "calibration"), ("a1_distribution", "fairness"),
                 ("a1_distribution", "a3_structural")):
        m, _ = sweep_eval(weights=w_over(pair, default_weights),
                          normalisation="threshold_relative", thresholds={}, ahs_band=0.75)
        ladder["pair::" + "+".join(pair)] = m
    full_ahs, or_rule = sweep_eval(_tag="full_havm_ahs", weights=default_weights,
                                   normalisation="threshold_relative", thresholds={},
                                   ahs_band=0.75)
    ladder["full_havm_ahs"] = full_ahs
    ladder["independent_or_rule"] = or_rule
    ladder["no_monitoring"] = evaluate([False] * len(eval_idx), eval_truth)

    for name in MONITORS:
        m, _ = sweep_eval(_tag=f"ablate::{name}",
                          weights=w_over([x for x in MONITORS if x != name], default_weights),
                          normalisation="threshold_relative", thresholds={}, ahs_band=0.75)
        ladder[f"ablate::{name}"] = m

    for k, m in ladder.items():
        print(f"   {k:<44} precision={m['precision']}  recall={m['recall']}  F1={m['f1']}")

    # Bootstrap over windows. With 35 evaluation windows a single reclassified window moves
    # F1 by roughly 0.02, so the headline differences in the ladder are the size of one
    # window. This quantifies whether any of them survives resampling.
    print("\n[EXP006b] bootstrap over windows (2,000 resamples) — is the integration gain real?")
    rng_b = np.random.default_rng(20260819)
    yt = np.asarray(eval_truth)
    comparisons = {}
    for challenger in ("independent_or_rule", "single::a1_distribution", "single::calibration"):
        a = np.asarray(decision_store["full_havm_ahs"], dtype=int)
        b = np.asarray(decision_store[challenger], dtype=int)
        diffs = []
        for _ in range(2000):
            idx = rng_b.integers(0, len(yt), len(yt))
            fa = evaluate(a[idx].tolist(), yt[idx].tolist())["f1"]
            fb = evaluate(b[idx].tolist(), yt[idx].tolist())["f1"]
            if fa is not None and fb is not None:
                diffs.append(fa - fb)
        lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
        comparisons[challenger] = {"delta_f1_mean": float(np.mean(diffs)),
                                   "ci95": [lo, hi],
                                   "excludes_zero": bool(lo > 0 or hi < 0),
                                   "n_resamples": len(diffs)}
        print(f"   AHS - {challenger:<26} dF1 {np.mean(diffs):+.3f}  "
              f"95% CI [{lo:+.3f}, {hi:+.3f}]  excludes zero: {lo > 0 or hi < 0}")
    ladder["_bootstrap_vs_challengers"] = comparisons

    write_json({
        "experiment_ids": ["EXP004", "EXP005", "EXP006"],
        "environment": environment_record(),
        "config_hash": sha256_obj(cfg),
        "monitor_config_hash": sha256_obj(registry["monitor_config"]),
        "ground_truth": "INJECTED: degraded iff a perturbation was applied",
        "window_bank": [{k: r[k] for k in ("window_id", "kind", "severity", "degraded", "raw")}
                        for r in records],
        "exp004_ahs_null_band_by_window_size": exp004,
        "exp005a_threshold_sensitivity": thresholds_sweep,
        "exp005b_normalisation_sensitivity": norm_sweep,
        "exp005c_weight_sensitivity": weight_sweep,
        "exp006_baselines_and_ablation": ladder,
    }, out / "metrics" / "EXP004-006_sensitivity.json")
    print(f"\n[G6] written to {out}/metrics/EXP004-006_sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
