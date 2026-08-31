"""Generate every figure from stored experiment results (BRIEF §42–43).

    python scripts/make_figures.py

No number is typed by hand: each figure reads the JSON an experiment wrote. Re-running an
experiment and re-running this script is the whole update path. Every figure answers a
stated research question, named in its caption line below.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "results" / "metrics"
FIGS = ROOT / "results" / "figures"
INK, ACCENT, WARN = "#22303f", "#3d6b8f", "#b4553f"


def load(name):
    path = METRICS / name
    if not path.exists():
        print(f"   skipped: {name} not found — run the experiment that produces it")
        return None
    return json.loads(path.read_text())


def finish(fig, ax_or_axes, name, caption):
    axes = ax_or_axes if isinstance(ax_or_axes, (list, np.ndarray)) else [ax_or_axes]
    for ax in np.ravel(axes):
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(colors=INK, labelsize=8)
    fig.tight_layout()
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{name}.png", dpi=160)
    plt.close(fig)
    print(f"   {name}.png — {caption}")


def fig_stability(d):
    """RQ4: is AHS stable enough for its own governance bands to mean anything?"""
    st = d["exp010_ahs_stability"]["by_window_count"]
    band = d["exp010_ahs_stability"]["governance_band_width"]
    ns = sorted(int(v["window_rows"]) for v in st.values())
    order = sorted(st.values(), key=lambda v: v["window_rows"])
    spans = [v["p05_p95"][1] - v["p05_p95"][0] for v in order]
    sds = [v["sd"] for v in order]

    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.4))
    a.plot(ns, spans, "o-", color=ACCENT, label="5–95% AHS span")
    a.axhline(band, color=WARN, ls="--", label=f"governance band width ({band:.2f})")
    a.set_xlabel("window size (rows)"); a.set_ylabel("AHS span on unchanged data")
    a.set_title("Noise against the decision bands", color=INK, fontsize=10)
    a.legend(fontsize=7, frameon=False)

    for v in order:
        b.scatter([v["window_rows"]] * len(v["scores"]), v["scores"], s=8,
                  color=ACCENT, alpha=0.5)
        b.scatter([v["window_rows"]], [v["mean"]], s=40, color=WARN, zorder=3)
    b.set_xlabel("window size (rows)"); b.set_ylabel("AHS")
    b.set_title("30 partitions per size, one distribution", color=INK, fontsize=10)
    finish(fig, (a, b), "fig01_ahs_stability",
           "AHS noise vs window size, against the governance band width (RQ4)")


def fig_thresholds(d):
    """RQ6: sensitivity against alert burden."""
    sw = d["exp005a_threshold_sensitivity"]
    bands = sorted(float(k) for k in sw)
    prec = [sw[str(b)]["precision"] for b in bands]
    rec = [sw[str(b)]["recall"] for b in bands]
    far = [sw[str(b)]["false_alarm_rate"] for b in bands]

    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    ax.plot(bands, prec, "o-", color=ACCENT, label="precision")
    ax.plot(bands, rec, "s-", color=INK, label="recall")
    ax.plot(bands, far, "^--", color=WARN, label="false-alarm rate")
    ax.set_xlabel("AHS review band"); ax.set_ylabel("rate")
    ax.set_title("Threshold sensitivity", color=INK, fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    finish(fig, ax, "fig02_threshold_sensitivity",
           "precision / recall / false-alarm rate vs AHS band (RQ6)")


def fig_ladder(d):
    """RQ1: does integration beat the alternatives?"""
    lad = {k: v for k, v in d["exp006_baselines_and_ablation"].items()
           if not k.startswith("_") and isinstance(v, dict) and v.get("f1") is not None}
    keys = ["single::fairness", "single::a1_distribution", "single::calibration",
            "independent_or_rule", "full_havm_ahs"]
    keys = [k for k in keys if k in lad]
    vals = [lad[k]["f1"] for k in keys]
    boot = d["exp006_baselines_and_ablation"].get("_bootstrap_vs_challengers", {})

    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    colours = [ACCENT] * (len(keys) - 1) + [WARN]
    ax.barh(range(len(keys)), vals, color=colours)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([k.replace("single::", "").replace("_", " ") for k in keys], fontsize=8)
    ax.set_xlabel("F1"); ax.set_xlim(0, 1)
    ci = boot.get("independent_or_rule", {}).get("ci95")
    subtitle = (f"AHS − OR-rule: ΔF1 {boot['independent_or_rule']['delta_f1_mean']:+.3f}, "
                f"95% CI [{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "")
    ax.set_title("Baseline ladder — " + subtitle, color=INK, fontsize=9)
    finish(fig, ax, "fig03_baseline_ladder",
           "detection F1 by configuration, with the bootstrap interval (RQ1)")


def fig_ood(d):
    """RQ3: do detector rankings transfer to tabular EHR?"""
    bake = d["exp007_ood_bakeoff"]
    groups = list(bake["groups"])
    dets = bake["ranking"]
    mat = np.array([[bake["groups"][g]["auroc"][x] for x in dets] for g in groups])

    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    im = ax.imshow(mat, cmap="RdBu", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(dets)))
    ax.set_xticklabels([x.replace("_", "\n") for x in dets], fontsize=7)
    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels([g.replace("_", " ") for g in groups], fontsize=8)
    for i in range(len(groups)):
        for j in range(len(dets)):
            ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if abs(mat[i, j] - 0.5) > 0.3 else INK)
    fig.colorbar(im, ax=ax, label="AUROC (0.5 = chance)")
    ax.set_title("OOD detector performance by clinical group", color=INK, fontsize=10)
    finish(fig, ax, "fig04_ood_bakeoff",
           "OOD AUROC per detector per group; 0.5 is chance (RQ3)")


def fig_ramp(d):
    """H3: does AHS track severity?"""
    part = d["part_b_injected"]
    sev = part["severities"]
    ahs = [w["ahs"] for w in part["windows"]]
    sat = [len(w["saturated"]) for w in part["windows"]]

    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.plot(range(len(ahs)), ahs, "o-", color=ACCENT, label="AHS")
    ax2 = ax.twinx()
    ax2.bar(range(len(sev)), sev, alpha=0.18, color=INK, label="injected severity")
    ax2.set_ylabel("injected severity", fontsize=8)
    for i, s in enumerate(sat):
        if s:
            ax.annotate(f"{s} sat.", (i, ahs[i]), textcoords="offset points",
                        xytext=(0, -14), ha="center", fontsize=6, color=WARN)
    ax.set_xlabel("window"); ax.set_ylabel("AHS")
    ax.set_title("AHS against a declared severity ramp (saturated components marked)",
                 color=INK, fontsize=9)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    finish(fig, ax, "fig05_severity_ramp",
           "AHS vs injected severity, with saturation counts (H3)")


def fig_scalability(d):
    """RQ7: how does monitoring cost scale?"""
    bs = d["exp009_scalability"]["by_window_size"]
    ns = sorted(int(k) for k in bs)
    secs = [bs[str(n)]["seconds"] for n in ns]
    rps = [bs[str(n)]["rows_per_second"] for n in ns]

    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.2))
    a.plot(ns, secs, "o-", color=ACCENT)
    a.set_xlabel("window size (rows)"); a.set_ylabel("seconds")
    a.set_title("Monitoring wall-clock", color=INK, fontsize=10)
    b.plot(ns, rps, "o-", color=WARN)
    b.set_xlabel("window size (rows)"); b.set_ylabel("rows / second")
    b.set_title("Throughput — fixed overhead dominates at small n", color=INK, fontsize=10)
    finish(fig, (a, b), "fig06_scalability",
           "monitoring cost and throughput vs window size (RQ7)")


def main() -> int:
    print("Generating figures from stored results ...")
    sens = load("EXP004-006_sensitivity.json")
    scal = load("EXP009-010_scalability_stability.json")
    ood = load("EXP007-008_ood_and_full_ahs.json")
    replay = load("EXP003_replay.json")

    if scal:
        fig_stability(scal); fig_scalability(scal)
    if sens:
        fig_thresholds(sens); fig_ladder(sens)
    if ood:
        fig_ood(ood)
    if replay:
        fig_ramp(replay)
    print(f"\nFigures in {FIGS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
