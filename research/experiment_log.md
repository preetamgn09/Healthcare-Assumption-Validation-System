# Experiment Log

Append-only. Results are never overwritten; a corrected run gets a new ID.

---

## EXP001 — D2 pipeline, baselines, model freeze (Gate 3)

**Date:** 2026-08-19 · **Config:** `configs/d2_diabetes.yaml` · **Seed:** 20260819
**Runtime:** ~35 s end to end on CPU (no GPU, single process)

**Objective.** Build a verified, versioned data pipeline for D2; train and compare three
prediction baselines; freeze one as the object of monitoring; emit the assumption
registry v0.1.

**Hypothesis.** None. This is infrastructure. No research claim is made or tested here.

**Dataset.** Diabetes 130-US Hospitals (UCI #296), 101,766 encounters, sha256
`0689e7ec…24df97`, provenance `MIRROR_UNVERIFIED` (see Provenance note below).

**Cohort.** 101,766 → 99,340. Dropped 2,423 encounters with discharge disposition
expired/hospice (readmission undefined) and 3 with invalid gender. Missing markers `?`
recoded to an explicit `Unknown` category rather than dropped, so that missingness
remains observable to fairness and structural monitoring.

**Domain split.** Source = non-emergency admissions (36,638 encounters); target/deployment
= emergency admissions (55,848); 6,854 encounters with unmapped/NULL admission source
excluded from the contrast. Source prevalence 0.1060. **Target prevalence was not
computed** — the deployment set is sealed at this gate.

**Train/validation split.** Patient-grouped, 25% validation:
27,530 / 9,108 encounters over 23,089 / 7,696 patients. Patient overlap between train and
validation: **0** (asserted by test). Prevalence 0.1056 / 0.1073.

**Results — source-domain validation (n = 9,108):**

| Model | AUROC | AUPRC | Brier | ECE |
|-------|-------|-------|-------|-----|
| Prevalence baseline | 0.5000 | 0.1073 | 0.0958 | 0.0016 |
| Logistic regression | 0.6606 | 0.2077 | 0.0921 | 0.0080 |
| **Gradient boosting (selected, frozen)** | **0.6720** | **0.2256** | **0.0910** | **0.0060** |

Selected by AUPRC on source validation. The deployment domain played no part in selection.

At the top-decile operating point (threshold 0.1937): TPR 0.244, FPR 0.083,
precision 0.261, 911 encounters flagged.

**Subgroup observation (validation, top-decile operating point).** ΔTPR between the two
largest race groups is ≈ 0.074 (AfricanAmerican 0.293, n=1,633; Caucasian 0.219, n=6,837),
with prevalence also differing (0.113 vs 0.106). Asian, Hispanic and Other were suppressed
under the declared minimum group size of 200. **This is a baseline observation, not a
finding** — it is uncorrected for case mix, measured at one arbitrary operating point, and
on one validation split. It is recorded because it is the quantity Gate 4 fairness
monitoring will track over time.

**Unexpected behaviour.** Pandas' default missing-value list converts the literal string
`None` to NaN. In `max_glu_serum` and `A1Cresult`, `None` means *the test was not
performed* — real information about clinical practice, and precisely the kind of structural
signal A3 monitoring exists to observe. Reading with the default settings silently collapsed
"not tested" and "not recorded" into one value. Fixed by `keep_default_na=False`, with a
regression test (`test_none_is_preserved_as_a_category_not_a_missing_value`) so it cannot
return unnoticed.

**Conclusion.** Pipeline is verified, deterministic and leakage-tested. Model performance
is consistent with the published range for 30-day readmission on this dataset (AUROC
mid-0.6s); the model is adequate as a monitoring subject, which is the only requirement.
No scientific claim follows from this experiment.

**Provenance note.** `archive.ics.uci.edu` was unreachable from the build environment, so
the file was obtained from a GitHub mirror and verified against published metadata: exact
row/column counts (101,766 × 50), exact column names, and the readmission distribution
reported by Strack et al. (`<30` = 11,357, `>30` = 35,545, `NO` = 54,864). The checksum is
recorded, so any future copy can be proven byte-identical. **Before any result enters the
report, re-fetch with `scripts/fetch_d2.py --source uci` and confirm the checksum**, then
set `provenance_status: UCI_VERIFIED`.

---

## EXP002 — Monitors A1 / A3 / calibration / fairness (Gate 4)

**Date:** 2026-08-19 · **Configs:** `configs/d2_diabetes.yaml`, `configs/monitors.yaml`
**Runtime:** ~90 s CPU · **Registry:** v0.2.0 (monitor config ingested)

**Objective.** Implement four monitors against the frozen model and characterise their
behaviour on a null control, the real deployment domain, and an injected positive control.

**Hypothesis.** None tested. This gate establishes whether the monitors respond correctly;
H1/H7 are only touched observationally.

**Seal.** The Gate 3 deployment seal was verified by hash and then opened, once. Recorded in
the registry's `validation_history` as `DEPLOYMENT_SEAL_OPENED`.

**Violation signals** (reference = training, n = 27,530):

| Comparison | n | A1 | A3 | Calib. | Fairness |
|---|---|---|---|---|---|
| null_control_validation | 9,108 | 0.024 | 0.000 | 0.120 | 1.000 |
| real_deployment_domain | 55,848 | 1.000 | 0.200 | 0.141 | 1.000 |
| injected_case_mix_shift | 36,236 | 1.000 | 0.200 | 1.000 | 1.000 |

**Result — headline numbers.**
- A1: max PSI 0.0048 (null) → 3.33 (deployment) → 13.65 (injected). Features above the PSI
  bound: 0 → 5 → 7. Significant under BH-FDR: 1 → 22 → 22 of 25.
- Calibration ECE: 0.0060 → 0.0071 → 0.0752 (bound 0.05).
- Fairness ΔTPR, deployment: race 0.104 (null band p95 = 0.128, **inside noise**);
  age 0.385 (band 0.110, **beyond noise**); gender 0.008 (band 0.017).
- A3 on deployment: unseen `admission_type_id=7`, unseen `diag_1_group=Other_E`,
  out-of-range on three utilisation counts. All `OBSERVED`.

**Conclusion.**
1. Large covariate drift with unchanged aggregate calibration — drift is not harm.
2. Significance and effect size diverge sharply at deployment n (22 vs 5 features).
3. The BRIEF-specified fairness threshold of 0.05 fires on a disparity that sits inside the
   permutation null band; the age disparity, which is real, would have been given the same
   violation value of 1.000 because the normalisation saturates.
4. The frozen model already exceeds the fairness bound in-distribution (ΔTPR 0.074), so an
   absolute-threshold monitor contributes a constant non-zero violation from day one.

**Unexpected behaviour.** The fairness monitor triggered on the null control. Initial
reading was "false positive"; it is not — fairness is a property of the current window, not
a two-sample comparison, so the trigger is a genuine in-distribution disparity measured
against an absolute bound. That distinction changed the Gate 5 design recommendation
(baseline-relative entry into the AHS) and is the most useful thing this experiment
produced.

**Change made mid-experiment.** `min_positives` gating and the permutation null band were
added after the first run showed race:Unknown (n = 328, 26 positives) driving a ΔTPR of
0.089. TPR is conditional on positives, so a row-count gate is the wrong instrument. Both
gates are now reported separately so the difference stays visible. The first-run numbers are
superseded, not deleted: they are the reason the gate exists.

---

## EXP003 — AHS, triage, governance, audit, end-to-end replay (Gate 5)

**Date:** 2026-08-19 · **Configs:** `configs/d2_diabetes.yaml`, `configs/monitors.yaml`
**Runtime:** ~4 min CPU · **Registry:** v0.3.0 (freeze baselines added)

**Objective.** Connect dataset → frozen model → monitors → AHS → triage → governance →
audit, and characterise the composite's behaviour on a homogeneous stream and on a declared
severity ramp.

**Hypotheses touched.** H3 (AHS monotone in severity), H9 (low-weight masking), H10
(separation reduces inappropriate escalation).

**Freeze baselines.** ECE 0.0060, ΔTPR 0.0745, measured in-distribution on validation.

**Part A — OBSERVED, 10 random-partition windows of the deployment domain.**
AHS mean 0.453, sd 0.058, range 0.402–0.612. Governance (separated): 6 windows in
GOVERNANCE_REVIEW, 3 in ABSTENTION_RECOMMENDED, 1 NORMAL — with no change in the underlying
distribution. Declared-weight AHS 0.685 vs renormalised 0.428 on window W000.

**Part B — INJECTED severity ramp, n held at 8,000.**
Severity 0.00 → AHS 0.432 and 0.629; 0.25 → 0.316; 0.50 → 0.175; 0.75 → 0.175; 1.00 → 0.241.
Monotone decreasing: **False**. At severity ≥ 0.50 all three contributing monitors saturate
at violation 1.000 and AHS floors at 0.175.

**Governance, identical monitor output, two policies:**

| | separated | collapsed |
|---|---|---|
| Part A: reached suspension | no | yes |
| Part B: windows in AUTOMATED_PREDICTION_SUSPENSION | 0 | 7 of 10 |
| Part B: windows in ABSTENTION_RECOMMENDED | 5 | 0 |

**Conclusion.**
1. AHS varies by 0.21 across windows drawn from one distribution — comparable to the width
   of a whole governance band. H1 and RQ4 cannot be addressed until this is characterised.
2. Absent monitors raise AHS by 0.26 under declared weights. The additive form cannot
   distinguish "assumption holds" from "not measured", and errs towards reassurance.
3. H3 falsified in both directions: noise below severity 0.5, saturation above it.
4. H10 supported: separation prevented 7 of 10 suspension recommendations. This is support
   for separation — cheap and structural — not for aggregation, which is where the
   framework claims novelty.

**Unexpected behaviour.** The first version of the ramp let window size shrink as severity
rose (8,000 → 4,957), confounding severity with sample size — both PSI and ΔTPR are noisier
in smaller windows, so the observed non-monotonicity could have been either. Rerun with n
held constant by weighted resampling; non-monotonicity persisted, and the cause is now
identified as noise plus saturation rather than an artefact of the perturbation design. The
confounded run is superseded, not deleted: it is why `perturb()` now takes `n_out`.

**Caveat.** One ramp, one seed, ten windows per part. Findings 1 and 3 need repetition
across seeds before they carry real weight; that is the first task of Gate 6.

---

## EXP004–EXP006 — Null band, sensitivity sweep, baseline ladder (Gate 6)

**Date:** 2026-08-19 · **Runtime:** ~6 min CPU · **Registry:** v0.3.0 (unchanged)

**Objective.** Characterise AHS noise; sweep thresholds, weights and normalisation; compare
AHS against the baseline ladder with confidence intervals.

**Design.** Raw metrics computed once per window and rescored under each policy, so every
configuration is compared on identical measurements. Window bank: 20 clean (validation,
resampled n=2,500) + 25 perturbed (5 severities x 5 seeds). Ground truth INJECTED: degraded
iff perturbed. 10 clean windows held out to calibrate null quantiles; 35 evaluated.

**EXP004 — AHS on clean windows by size:** sd 0.053 / 0.040 / 0.079 / 0.076 / 0.070 at
n = 500 / 1,000 / 2,500 / 5,000 / 10,000; minimum observed AHS 0.693 at n=500 and 0.723 at
n=2,500, both below the 0.75 review band. Confounded above ~2,500 by pool exhaustion — the
clean pool is 9,108 rows resampled with replacement — so no claim is made about the
relationship between window size and noise beyond that range.

**EXP005a — threshold sweep:** precision 1.00 with recall 0.76→0.84 over bands 0.50–0.75 at
zero false alarms; precision falls to 0.77 and false-alarm rate rises to 0.70 by band 0.95.

**EXP005b — normalisation (RQ5b / H5):** threshold_relative, soft_exponential and
empirical_quantile all reach F1 = 0.913 at their best band (0.75 / 0.80 / 0.60). No
difference. H5 not supported; the hypothesis was badly posed, since all three are monotone
in the metric and therefore rank windows identically below saturation.

**EXP005c — weights (RQ5 / H4):** named configurations F1 0.840–0.913; 197 random Dirichlet
draws gave F1 mean 0.839, sd 0.084, range 0.276–0.936.

**EXP006 — ladder (RQ1 / H1):** full AHS F1 0.913 (precision 1.00, recall 0.84);
independent OR-rule 0.898 (0.92 / 0.88); best single monitor 0.889. Bootstrap over windows,
2,000 resamples: ΔF1 vs OR-rule +0.025, 95% CI [0.000, 0.085]; vs A1 alone +0.025, CI
[0.000, 0.085]; vs calibration alone +0.025, CI [0.000, 0.080]. **No interval excludes
zero.**

**Ablation:** removing A3 or calibration moves F1 from 0.913 to 0.898; removing fairness to
0.889. A3 alone has recall 0 — correct, since the perturbation changes case mix, not schema.

**Conclusion.**
1. H1 not supported on D2: the integration advantage is one window wide and does not survive
   resampling. AHS trades recall for precision relative to the OR-rule, which is a real
   property but a different claim.
2. H5 not supported, and restated: normalisation cannot affect detection at an optimised
   band because all candidates are monotone; it affects severity resolution above the bound.
3. H4 survives moderate weight variation but a poor draw takes F1 to 0.276 — weights are
   load-bearing and unconstrained.
4. Clean in-distribution windows fall below the review band at small window sizes.

**Unexpected behaviour.** A test caught a real bug before it reached a result: with
`empirical_quantile` selected and no null distribution calibrated for a monitor, `rescore`
raised instead of falling back. The sweep never hit the path because all four monitors had
null distributions. Now falls back to the threshold rule explicitly — inventing a quantile
from nothing would have put a fabricated number into the AHS.

**Caveat.** 35 evaluation windows, one perturbation family, one dataset. These results
bound what D2 can say; they are not a general finding about HAVM.

---

## EXP007–EXP008 — OOD bake-off (RQ3) and the complete seven-monitor AHS (Gate 7, D2 portion)

**Date:** 2026-08-19 · **Runtime:** ~5 min CPU · **Registry:** v0.4.0

**Why this and not the temporal replay.** Gate 7 was scoped as the BRFSS replay. BRFSS is
not downloaded and cdc.gov is unreachable from this environment, so RQ2 remains unstarted.
This gate took the most valuable unblocked work instead: completing the monitor set and
running RQ3, for which D2 — a real EHR extract — is the right substrate.

**EXP007 — OOD detector AUROC by clinically defined group (fixed before scoring):**

| Group | mahal. | knn | iForest | entropy | max softmax | energy |
|---|---|---|---|---|---|---|
| Paediatric & adolescent | 0.930 | 0.431 | 0.609 | 0.235 | 0.235 | 0.802 |
| Rare specialty | 0.548 | 0.545 | 0.522 | 0.538 | 0.538 | 0.396 |
| Extreme prior utilisation | 0.786 | 0.946 | 0.656 | 0.979 | 0.979 | 0.016 |
| Mean | 0.755 | 0.641 | 0.596 | 0.584 | 0.584 | 0.405 |

Uncertainty family mean 0.524; distance/density family mean 0.664. `unseen_admission_type`
had 18 members in deployment, below the minimum of 50, and was dropped.

**EXP008 — complete monitor set on the deployment domain:** violations a1 1.000,
a2 0.780, a3 0.200, a4 0.000 (SIMULATED), ood 0.267, calibration 0.141, fairness 1.000.
AHS: four monitors with missing-as-zero 0.677, four renormalised 0.412, **seven measured
0.481**. A2 AUROC 0.649 against a frozen 0.672 (delta 0.023, inside the 0.05 bound); the
label-free score PSI drove its violation, so label-blind and label-available agreed here.

**Conclusion.**
1. H8 supported. Uncertainty-based OOD detection is at chance on this tabular EHR extract,
   replicating Ulmer et al. in a new direction (shift detectors rather than UQ methods).
2. Predictive entropy is *inverted* on the paediatric group (AUROC 0.235): the model is more
   confident on the age band least represented in training. Silent failure, measured.
3. The brief's energy score averages 0.405 and hits 0.016 on one group — worse than chance.
   Computed on a logistic regression, since the frozen tree model has no logit vector; the
   substitution is reported everywhere the number appears.
4. Rare specialty defeats every detector (0.52–0.55).

**Correction to EXP003 Finding 2.** That experiment concluded absent monitors bias AHS
towards false reassurance. Measuring all seven shows both approximations are biased and they
bracket the truth: missing-as-zero overstates health (0.677 vs 0.481), renormalisation
understates it (0.412), because renormalisation assumes absent monitors resemble present
ones and here they scored better. Direction of error is data-dependent. EXP003's entry is
left as written; this correction is recorded against it.

**Unexpected behaviour.** A test asserting that predictive entropy and max softmax are
monotone equivalents failed at exact equality — mathematically tied values differ in the last
floating-point bits, so a few ranks swap. Rank correlation 0.99999; tolerance set accordingly
and the reason recorded rather than the assertion weakened silently.

---

## EXP009–EXP010 — Scalability and AHS stability (Gate 8)

**Date:** 2026-08-19 · **Runtime:** ~4 min CPU · **Hardware:** recorded in the results JSON

**Objective.** Measure monitoring cost against window and reference size (RQ7), and repeat
the Gate 5 stability observation with enough seeds to be usable.

**EXP010 — 30 independent partitions of the deployment domain per window size:**

| Windows | Window size | mean AHS | sd | 5–95% span |
|---|---|---|---|---|
| 20 | ≈2,792 | 0.506 | 0.073 | 0.206 |
| 10 | ≈5,584 | 0.442 | 0.050 | 0.139 |
| 5 | ≈11,169 | 0.422 | 0.017 | 0.040 |

Governance band width = 0.25.

**EXP009 — monitoring cost:** 0.61 s at n=1,000 rising to 1.80 s at n=55,848 (1,647 →
31,071 rows/s); peak RSS flat at 365 MB; reference size 2,753→27,530 rows changes wall-clock
by less than the measurement noise; seven monitors cost 1.09 s at n=5,000 against 0.55 s for
four, plus a one-off 0.7 s detector fit. Full pipeline 1.8 s.

**Conclusion.**
1. AHS noise shrinks with window size, resolving both the EXP003 single-seed limitation and
   the EXP004 pool-exhaustion confound. On this substrate windows need roughly 10,000 rows
   before the 5–95% span on unchanged data (0.040) is small relative to the band width
   (0.25); at ≈2,800 rows the span is 0.206, or 82% of the band.
2. AHS is biased by window size as well as noisier: mean 0.422 at ≈11,000 rows vs 0.506 at
   ≈2,800 on identical data. Scores computed at different window sizes are different
   quantities and cannot share a threshold — the framework defines the score without
   reference to window size at all.
3. Monitoring cost is dominated by fixed overhead: 56x the rows costs 3x the time. There is
   no computational argument for small windows, and there is a statistical argument against
   them. Both favour fewer, larger windows.

**Also delivered.** Six figures generated programmatically from stored results
(`scripts/make_figures.py`), a one-command reproduction (`scripts/reproduce_all.sh`), and
`scripts/prepare_d1.py`, which converts downloaded BRFSS files and inventories their real
columns per year. The last downloads nothing on purpose: hard-coding unverifiable CDC URLs
would be the same unchecked assumption this project exists to detect.
