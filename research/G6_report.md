# Gate 6 — Stage Report (BRIEF §65)

## 1. What was implemented

A rescoring layer that recomputes violations, AHS and alert decisions from **cached raw
metrics**, so every configuration in the sweep is compared on identical measurements rather
than on separate monitor runs. On top of it: the AHS null-band characterisation (EXP004),
threshold / normalisation / weight sensitivity (EXP005), and the baseline ladder with
ablation and bootstrap confidence intervals (EXP006).

**This gate answers RQ1, RQ5, RQ5b and RQ6 on D2. The headline answer to RQ1 is negative.**

## 2. Files created

| Path | Purpose |
|------|---------|
| `src/havm/sweep.py` | Rescore cached raw metrics under any policy; detection metrics |
| `scripts/run_g6.py` | EXP004–EXP006 |
| `tests/test_sweep.py` | 12 tests |

**Modified:** `src/havm/monitors/base.py` gained the `soft_exponential` normalisation.

## 3. Tests executed

`python -m pytest tests/ -q` → **78 passed** (66 prior, 12 new), ~4 s.

One test found a real bug before it reached a result: when `empirical_quantile` is selected
but no null distribution has been calibrated for a monitor, `rescore` raised instead of
falling back. In the sweep all four monitors happened to have null distributions, so the
path was never exercised — the test found it anyway. It now falls back to the threshold
rule explicitly rather than inventing a quantile.

## 4. Results

### EXP004 — AHS null band vs window size (clean windows only)

| Window size | mean AHS | sd | range |
|---|---|---|---|
| 500 | 0.792 | 0.053 | 0.693 – 0.888 |
| 1,000 | 0.863 | 0.040 | 0.793 – 0.931 |
| 2,500 | 0.883 | 0.079 | 0.723 – 0.989 |
| 5,000 | 0.863 | 0.076 | 0.765 – 0.990 |
| 10,000 | 0.890 | 0.070 | 0.791 – 0.991 |

**Finding 5 — clean windows fall below the review band.** At n = 500 the AHS range reaches
0.693, and at n = 2,500 it reaches 0.723, both under the declared review band of 0.75. A
system running this configuration would open a governance review on in-distribution data
with nothing wrong.

**Important caveat on this table, stated because it changes what can be concluded:** the
clean pool is the validation set, 9,108 rows, resampled with replacement. Beyond a few
thousand, larger windows re-draw the same rows, so the effective sample size is capped by
the pool and the standard deviation stops falling for reasons that have nothing to do with
monitoring. The correct reading is therefore narrow — *AHS noise on this substrate is
around 0.04–0.08 sd and does not visibly shrink over the range we can test* — not the
general claim that AHS noise is independent of window size. Testing that properly needs D1,
where clean windows can be drawn without replacement at scale.

### EXP005a — Threshold sensitivity (RQ6)

45-window bank: 20 clean, 25 perturbed at five severities. Ground truth is `INJECTED` and
declared: degraded iff a perturbation was applied. Ten clean windows are held out to
calibrate the null distribution, leaving 35 evaluation windows.

| AHS band | precision | recall | false-alarm rate | alert rate |
|---|---|---|---|---|
| 0.50 | 1.00 | 0.76 | 0.00 | 0.54 |
| 0.60 | 1.00 | 0.80 | 0.00 | 0.57 |
| 0.70 | 1.00 | 0.80 | 0.00 | 0.57 |
| **0.75** | **1.00** | **0.84** | **0.00** | 0.60 |
| 0.80 | 0.92 | 0.88 | 0.20 | 0.69 |
| 0.90 | 0.82 | 0.92 | 0.50 | 0.80 |
| 0.95 | 0.77 | 0.96 | 0.70 | 0.89 |

A clean sensitivity/alert-burden trade-off. Notably the BRIEF-specified 0.75 sits at the
knee — which is a coincidence worth naming as such, not a vindication: the curve is
specific to this bank, this perturbation and this weighting, and Finding 5 shows the same
band opening reviews on clean data at smaller window sizes.

### EXP005b — Normalisation sensitivity (RQ5b) — **my own hypothesis, not supported**

| Normalisation | best band | F1 | precision | recall |
|---|---|---|---|---|
| threshold_relative | 0.75 | 0.913 | 1.000 | 0.840 |
| soft_exponential | 0.80 | 0.913 | 1.000 | 0.840 |
| empirical_quantile | 0.60 | 0.913 | 1.000 | 0.840 |

Identical. H5 predicted normalisation would dominate the weights; **it made no difference
to detection at all.** The reason is now isolated in a test: all three are monotone in the
raw metric, so below saturation they order windows identically and only move where the band
must sit. H5 was badly posed — it should have been about *severity resolution and
interpretability*, not detection. Restated for D1:

> Normalisation choice does not affect which windows are ranked worse, and therefore cannot
> affect detection at an optimised band. It affects whether severity remains legible above
> the bound — `threshold_relative` collapses everything past the threshold to a single
> value, which is the mechanism behind EXP003 Finding 3.

That restatement is testable and is now covered by a dedicated test.

### EXP005c — Weight sensitivity (RQ5) — **H4 not supported**

| Configuration | precision | recall | F1 |
|---|---|---|---|
| equal | 0.92 | 0.88 | 0.898 |
| brief default | 1.00 | 0.84 | 0.913 |
| behaviour-weighted | 0.84 | 0.84 | 0.840 |
| input-weighted | 1.00 | 0.80 | 0.889 |
| 197 random Dirichlet draws | — | — | mean 0.839, sd 0.084, **range 0.276 – 0.936** |

H4 claimed AHS is robust to moderate weight variation. Across the named configurations the
spread is modest (0.840–0.913), so the hypothesis survives in the "moderate" regime it was
stated for. But an unlucky random weighting drops F1 to 0.276 — the composite can be made
almost useless by a weighting nobody would notice was bad, because nothing in the framework
constrains the choice. Weights are not a tuning detail; they are load-bearing and
unspecified.

### EXP006 — Baseline ladder and ablation (RQ1) — **H1 not supported**

| Configuration | precision | recall | F1 |
|---|---|---|---|
| no monitoring | — | 0.00 | — |
| single: a3_structural | — | 0.00 | — |
| single: fairness | 0.79 | 0.60 | 0.682 |
| single: a1_distribution | 1.00 | 0.80 | 0.889 |
| single: calibration | 1.00 | 0.80 | 0.889 |
| pair: a1 + calibration | 1.00 | 0.80 | 0.889 |
| pair: a1 + a3 | 1.00 | 0.80 | 0.889 |
| pair: a1 + fairness | 0.85 | 0.88 | 0.863 |
| independent OR-rule | 0.92 | 0.88 | 0.898 |
| **full HAVM (AHS)** | **1.00** | **0.84** | **0.913** |

Bootstrap over the 35 evaluation windows, 2,000 resamples:

| Comparison | ΔF1 | 95% CI | excludes zero |
|---|---|---|---|
| AHS − independent OR-rule | +0.025 | [+0.000, +0.085] | **no** |
| AHS − best single (A1) | +0.025 | [+0.000, +0.085] | **no** |
| AHS − calibration alone | +0.025 | [+0.000, +0.080] | **no** |

**Finding 6 — the integration advantage is one window wide and does not survive
resampling.** With 35 evaluation windows a single reclassified window moves F1 by about
0.02, and the entire observed advantage is 0.025. Every confidence interval touches zero.
On this substrate, with this perturbation, **AHS is not measurably better than alarming on
any single monitor, nor better than an OR-rule over independent detectors.** What it does
do is trade recall for precision (1.00/0.84 against the OR-rule's 0.92/0.88) — a real and
possibly desirable property, but a different claim from the one the framework makes.

**Ablation:** removing A3 or calibration slightly *improves* F1 (0.898 vs 0.913 — again one
window); removing fairness raises precision to 1.00 and drops recall to 0.80. A3 alone
detects nothing, correctly: the perturbation changes case mix, not schema. No component is
shown to earn its place.

## 5. Scientific assumptions

1. **Ground truth is injected and binary.** "Degraded" means "a perturbation was applied",
   not "the model became clinically unsafe". Real-world detection performance is not what
   this measures.
2. **One perturbation family** (older, higher-utilisation case mix). A different family
   would exercise different monitors — which is exactly why A3 scores zero.
3. **Permutation bands are disabled during the sweep** for runtime, so fairness alerts here
   are threshold-based only and the noise discounting of EXP002 is not applied.
4. **Clean windows are resampled with replacement** from 9,108 validation rows; see the
   EXP004 caveat.
5. **35 evaluation windows** is a small sample for precision/recall. The bootstrap is
   reported precisely so no result is read as more solid than it is.

## 6. Engineering assumptions

1. Raw metrics computed once and rescored — every configuration sees identical measurements.
2. Null quantiles calibrated on 10 clean windows held out from evaluation.
3. Ablation renormalises weights over the remaining monitors.

## 7. Known limitations

1. **No temporal replay.** Unchanged, and now clearly the limiting factor: RQ2 (detection
   speed) is untouched, and RQ1's negative result rests on 35 injected windows rather than
   a deployment trajectory.
2. **Single dataset, single perturbation family, single seed per window.**
3. **The EXP004 pool-exhaustion confound** limits what the null-band table can claim.
4. **A2, A4 and OOD still absent** — and EXP003 Finding 2 quantified what their absence
   costs the score.
5. **Provenance still `MIRROR_UNVERIFIED`.**

## 8. Computational cost

~6 minutes single-threaded: 145 monitor runs (100 for EXP004, 45 for the bank), then ~250
rescorings and 6,000 bootstrap evaluations, all cheap. Caching raw metrics is what made the
sweep affordable — recomputing monitors per configuration would have taken hours.

## 9. Where the project now stands

Four hypotheses have been tested on D2. Three are unsupported and one is supported:

| | |
|---|---|
| H1 integration improves precision | **not supported** — CI touches zero |
| H3 AHS monotone in severity | **falsified** — noise below, saturation above |
| H4 robust to weights | **partly** — survives moderate variation, fails at the extremes |
| H5 normalisation dominates weights | **not supported** — no detection effect at all |
| H9 low-weight masking | **confirmed analytically and numerically** |
| H10 separation reduces escalation | **supported** — 7 of 10 suspensions avoided |

The pattern is consistent and worth stating plainly: **the parts of HAVM that are cheap and
structural — a shared registry, co-located monitors, separating detection from governance,
an audit trail — hold up. The part that is novel — composite scoring — does not yet earn
its place.** That is a publishable finding, and it is the one the capstone is currently in
a position to defend.

## 10. Recommended next stage

**Gate 7 — D1 (BRFSS) temporal replay.** Everything above is now bounded by the absence of
a time axis. RQ2 is unstarted; RQ1's negative result deserves a second substrate before it
is reported as a conclusion; and EXP004's confound resolves only where clean windows can be
drawn without replacement.

Nothing further on D2 will change the picture materially. The next real information comes
from BRFSS.
