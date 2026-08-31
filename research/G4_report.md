# Gate 4 — Stage Report (BRIEF §65)

## 1. What was implemented

Four monitors — A1 distributional, A3 structural, calibration, fairness — behind a single
`MonitorResult` contract, all reading configuration from the assumption registry. One
experiment, EXP002, running each monitor across three comparisons: a null control, the real
deployment domain, and an injected positive control.

This is **not** a replay. D2 has no time axis, so there are no windows, no detection delay
and no alert-volume result. Those require D1 (BRFSS), which has not been downloaded.

## 2. Files created

| Path | Purpose |
|------|---------|
| `configs/monitors.yaml` | Every threshold, bin count, FDR setting and the normalisation function |
| `src/havm/monitors/base.py` | `MonitorResult` contract, normalisation, Benjamini–Hochberg FDR |
| `src/havm/monitors/distribution.py` | A1: PSI, KS/χ² with FDR, linear-time MMD |
| `src/havm/monitors/structural.py` | A3 structural, calibration, fairness monitors |
| `scripts/run_g4.py` | EXP002 runner; verifies and opens the deployment seal |
| `tests/test_monitors.py` | 16 analytic tests |

**Modified:** none of Gate 3's code. The registry gained `monitor_config` and a
`validation_history` entry recording that the seal was opened.

## 3. Tests executed

`python -m pytest tests/ -q` → **47 passed** (31 from Gate 3, 16 new), ~5 s.

New analytic guarantees: PSI → 0 when P = Q and > 0.20 under a 1.5σ mean shift; PSI
non-negative over 20 random pairs; MMD² → 0 when P = Q and monotone in separation; BH
rejects nothing under the global null where uncorrected testing rejects ~25 of 500;
normalisation saturates exactly at the threshold; `MonitorResult` refuses a violation
outside [0,1]; fairness reports no disparity when group membership is exchangeable, detects
an injected TPR gap, and suppresses a group that passes the row gate but fails the
positive-count gate.

## 4. Results — EXP002

Reference = training set (non-emergency admissions, n = 27,530).

| Comparison | A1 | A3 | Calibration | Fairness |
|---|---|---|---|---|
| Null control (validation, n=9,108) | 0.024 | 0.000 | 0.120 | **1.000 ⚠** |
| Real deployment (ER, n=55,848) | **1.000** | **0.200** | 0.141 | **1.000** |
| Injected case-mix shift (n=36,236) | **1.000** | **0.200** | **1.000** | **1.000** |

Violation signals in [0,1]; bold = triggered against its declared threshold.

### Four findings worth carrying forward

**(a) Drift is not harm.** The deployment domain drives max PSI to 3.33 with 5 of 25
features beyond the PSI threshold — a large, unambiguous covariate shift — while aggregate
calibration is essentially unchanged (ECE 0.0071 vs 0.0060 on validation, both far below
the 0.05 bound). An AHS weighted towards A1 would report severe degradation on a model
whose probability outputs remained trustworthy in aggregate. This is Rabanser et al.'s
detect-versus-judge-harmful distinction appearing as a measurement, and it is direct
evidence bearing on H1: integration only helps if the composite can tell these apart.

**(b) Statistical significance is worthless at this sample size.** 22 of 25 features are
significant under BH-FDR; only 5 exceed the PSI effect-size threshold. On the null control
the ratio behaves correctly (1 of 25 significant, 0 material), so the FDR correction is
working — the divergence is a property of n, not a bug. The violation signal follows effect
size for this reason; significance is retained as evidence only.

**(c) The specified fairness threshold alarms on noise.** Race ΔTPR in the deployment
domain is 0.104 — comfortably past the BRIEF-specified 0.05 bound, giving a violation of
1.000 — but the permutation reference band puts the 95th percentile of ΔTPR under label
exchangeability at **0.128**. The observed disparity is *inside* what sampling noise
produces. A monitoring system using the specified threshold would escalate this, and it
would be wrong. Age tells the opposite story and is the real signal: ΔTPR 0.385 against a
band of 0.110, a genuine and large subgroup effect — occurring while aggregate calibration
stayed within bounds, which is the pattern RQ8/H7 predicts.

**(d) The model violates its own fairness policy at freeze time.** On the validation set —
in-distribution, no shift of any kind — race ΔTPR is 0.074, already past the 0.05 bound.
So the fairness violation signal is non-zero before deployment begins, and AHS would start
below 1.0 for reasons having nothing to do with drift. This exposes a structural problem in
the AHS design that neither paper addresses: **absolute-threshold monitors and
change-detection monitors are different instruments and cannot be summed as though they
were the same.** Recommendation for Gate 5 — fairness and calibration signals enter the AHS
as *change from the frozen baseline*, with the absolute violation reported separately as a
policy-compliance fact.

### Real structural changes detected (A3, `OBSERVED`)

Unseen category `admission_type_id = 7` and `diag_1_group = Other_E`; out-of-range values in
`num_lab_procedures`, `number_outpatient`, `number_inpatient`. Not injected — genuine
consequences of the domain difference, found by a monitor that never sees the model.

### Positive control behaved as designed

The injected shift (older case mix, higher prior utilisation) moved max PSI to 13.65 and
pushed ECE to 0.075, past the bound. The perturbation was specified by its effect on the
data-generating process, not by the statistic it was meant to move; the calibration response
is a consequence of that, not a target.

## 5. Scientific assumptions

1. **PSI drives the A1 violation signal, not p-values** — deliberate, see (b).
2. **The permutation band tests exchangeability of group labels**, so it conflates genuine
   case-mix differences with model behaviour. It answers "is this beyond noise", not "is
   this unfair". Separating those is triage's job at Gate 5.
3. **Calibration and fairness need labels** a live deployment would not have at monitoring
   time. Treated as retrospective measurements; a label-blind variant is required before
   any claim about real-time detection.
4. **Normalisation is `threshold_relative` and saturates at 1.0.** Every violation above the
   bound is indistinguishable from every other — H3's predicted saturation, visible already:
   three different comparisons all report fairness = 1.000 despite ΔTPR of 0.074, 0.385 and
   0.292.

## 6. Engineering assumptions

1. Linear-time MMD estimator with median-heuristic bandwidth; unbiased, so it may go
   slightly negative under the null — reported unclipped.
2. PSI bins fixed on the reference, ε = 1e-6 floor; near-constant features return 0.
3. A3 violation is the fraction of contract columns affected — already on [0,1], no
   threshold division.
4. Permutation band at B = 200; adequate for a p95 estimate, not for a tail p-value.

## 7. Known limitations

1. **No temporal replay.** The centrepiece experiment still cannot run on D2.
2. **The seal has been opened.** It was verified by hash first and the event is in the
   registry's validation history, but the deployment domain is no longer naive. Any further
   modelling decision taken with knowledge of these results must be declared.
3. **Fairness saturation** hides severity, as above.
4. **A2, OOD, A4 not implemented**, by plan.
5. **Provenance is still `MIRROR_UNVERIFIED`** — unchanged from Gate 3, still needs the UCI
   re-fetch before anything is reported.
6. **B = 200 permutations** is the coarsest component of the fairness result.

## 8. Computational cost

EXP002 runs in ~90 s single-threaded, < 2 GB RAM. The permutation bands dominate (~60%);
the linear MMD is negligible, which is why it was chosen over the quadratic form.

## 9. Recommended next stage

**Gate 5 — AHS, triage, governance, audit.** Three design decisions now have evidence behind
them rather than being guesses:

1. Baseline-relative entry for absolute-threshold monitors, per finding (d).
2. A triage stage that can distinguish drift from harm, per finding (a) — without it the
   composite inherits A1's alarm wholesale.
3. Saturation must be measured and reported, not designed away.

In parallel: download BRFSS. Every remaining research question with a temporal component is
blocked on it.
