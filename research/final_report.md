# Empirically Testing a Multi-Assumption Healthcare AI Monitoring Framework

**HAVM capstone — research report support (BRIEF §61)**
Status: complete on substrate D2. The temporal substrate D1 (BRFSS) has not been acquired,
so RQ2 is unanswered and is reported as such throughout.

Every number below is taken from a file in `results/`, produced by a script in `scripts/`.
Nothing was typed by hand. Re-running `scripts/reproduce_all.sh` regenerates all of it.

---

## 1. What was investigated

HAVM is proposed in the reviewed literature as a five-layer, assumption-first monitoring
architecture for deployed healthcare AI. Its central quantitative claim is that integrating
complementary assumption monitors into a single composite score — the Assumption Health
Score — detects clinically meaningful degradation more reliably or earlier than isolated
monitoring.

This project treats that claim as a hypothesis rather than a design. The framework was
implemented completely enough to be tested, then tested in ways capable of showing it does
not work.

**Provenance note that conditions the whole project.** The AHS formula, the A1–A4 taxonomy,
the severity weights and every threshold were specified in the project brief and appear in
**neither** supplied version of the HAVM paper — both organise the framework as layers L1–L5
with no composite score and no numeric bounds. They are therefore treated as design
decisions of this project (`POLICY`), not as claims inherited from published work. See
`paper_analysis.md` §0.

## 2. Methodology

A modular implementation of the full chain: assumption registry → frozen prediction model →
seven monitors → AHS aggregation → harm triage → governance state machine → audit trail,
driven by a replay engine. Every threshold and weight lives in configuration and is read
from the registry; `src/` contains no hardcoded bound. 92 tests cover the analytic
guarantees (P = Q ⇒ MMD → 0, perfect calibration ⇒ ECE → 0, AHS = 1 when nothing is
violated, and so on), leakage, determinism, and audit completeness.

Evidence is tagged throughout as `OBSERVED`, `INJECTED`, `SIMULATED` or `POLICY`, and the
categories are never mixed in a result.

## 3. Data

**D2 — Diabetes 130-US Hospitals (UCI #296)**, CC BY 4.0: a real EHR extract from the Cerner
Health Facts warehouse, 101,766 encounters across 130 hospitals.

Cohort: 101,766 → 99,340 after removing 2,423 expired/hospice discharges (readmission
undefined) and 3 invalid-gender records. Missing markers were kept as an explicit category
rather than imputed or dropped, so missingness stays visible to fairness and structural
monitoring.

Split: source domain = non-emergency admissions (36,638 encounters); deployment domain =
emergency admissions (55,848 encounters, 40,371 patients); 6,854 encounters with unmapped
admission source excluded. Source split by **patient** into 27,530 training and 9,108
validation encounters (23,089 / 7,696 patients, zero patient overlap, asserted by test).

**Limitation carried throughout: D2 has no time axis.** It carries no date column, and
`encounter_id` ordering is an unverifiable proxy this project refuses to use. Every temporal
research question is therefore unanswered. D1 (BRFSS) was selected to supply real monthly
timestamps and a documented 2011 methodology break, and has not been acquired.

**Provenance is `MIRROR_UNVERIFIED`.** The archive host was unreachable from the build
environment; the file was obtained from a mirror and verified against published metadata
(exact row and column counts, exact column names, and the published readmission
distribution). The SHA-256 is recorded and the pipeline refuses to run on a mismatch. A
re-fetch from the canonical source is required before publication.

## 4. Experimental setup

Task: 30-day readmission (positive class `<30`), chosen over alternatives on label
unambiguity, prevalence, and support for calibration and subgroup analysis.

| Model | AUROC | AUPRC | Brier | ECE |
|---|---|---|---|---|
| Prevalence baseline | 0.5000 | 0.1073 | 0.0958 | 0.0016 |
| Logistic regression | 0.6606 | 0.2077 | 0.0921 | 0.0080 |
| **Gradient boosting (frozen)** | **0.6720** | **0.2256** | **0.0910** | **0.0060** |

Selected on source-domain validation by AUPRC, then frozen and never retrained. Performance
is consistent with the published range for this task; the model is the object of monitoring,
not the contribution.

The deployment domain was **sealed** at freeze time — its hash recorded, its prevalence not
computed — and opened once, deliberately, with the event written to the registry's
validation history. That seal is what makes the deployment comparison a simulation of
deployment rather than a retrospective fit.

## 5. Baselines compared

No monitoring · each monitor alone · monitor pairs · an OR-rule over independent detectors ·
the full AHS. Governance was additionally run in two variants on identical monitor output:
`separated` (detect → judge harm → govern) and `collapsed` (detect → act).

## 6. Results

### 6.1 Integration does not measurably improve detection (RQ1)

45-window bank (20 clean, 25 perturbed at five severities), 35 evaluated, `INJECTED` ground
truth.

| Configuration | precision | recall | F1 |
|---|---|---|---|
| single: fairness | 0.79 | 0.60 | 0.682 |
| single: a1_distribution | 1.00 | 0.80 | 0.889 |
| single: calibration | 1.00 | 0.80 | 0.889 |
| independent OR-rule | 0.92 | 0.88 | 0.898 |
| **full HAVM (AHS)** | 1.00 | 0.84 | **0.913** |

Bootstrap over windows, 2,000 resamples: ΔF1 versus the OR-rule **+0.025, 95% CI
[0.000, 0.085]**; versus the best single monitor +0.025, CI [0.000, 0.085]. **No interval
excludes zero.** One reclassified window moves F1 by roughly 0.02, so the entire observed
advantage is the width of a single window. AHS does trade recall for precision
(1.00/0.84 against 0.92/0.88) — a real property, but a different claim from the one the
framework makes.

**H1 is not supported on this substrate.**

### 6.2 Detector rankings do not transfer to tabular EHR (RQ3)

Six detectors, OOD groups defined by clinical criteria fixed before scoring. Mean AUROC
across groups:

| mahalanobis | knn | isolation forest | pred. entropy | max softmax | energy |
|---|---|---|---|---|---|
| **0.755** | 0.641 | 0.596 | 0.584 | 0.584 | 0.405 |

Uncertainty family mean **0.524** — chance — against 0.664 for distance and density methods.
This replicates the corpus's one clinical data point (uncertainty estimation failing as OOD
detection on tabular EHR) in a new direction.

Two results deserve separate emphasis:

- **The model is most confident where patients are least represented.** On paediatric and
  adolescent patients, predictive entropy reaches AUROC **0.235** — inverted, not merely
  uninformative. This is the silent-failure mode the literature describes, measured.
- **The brief-specified energy score averages 0.405** and reaches 0.016 on one group. It was
  computed on a logistic regression, because the frozen tree model produces no logit vector
  and applying the published formulation to it would be a category error; the substitution
  is reported wherever the number appears.

No detector handled the rare-specialty group (0.52–0.55 across the board).

**H8 is supported.**

### 6.3 AHS is unstable and window-size dependent (RQ4)

Thirty independent partitions of the deployment domain per window size, all from one
distribution — a well-behaved score should be flat.

| Window size | mean AHS | sd | 5–95% span |
|---|---|---|---|
| ≈2,792 | 0.506 | 0.073 | **0.206** |
| ≈5,584 | 0.442 | 0.050 | 0.139 |
| ≈11,169 | 0.422 | 0.017 | **0.040** |

Governance band width (review − suspension) = 0.25.

Two findings. First, at ≈2,800 rows the score's noise on **unchanged data** consumes 82% of
the entire governance band; at ≈11,000 rows, 16%. Second, mean AHS *rises* as windows shrink
— the score is biased by window size as well as noisier, so a daily and a weekly AHS are
different quantities that cannot share a threshold. The framework defines the score without
reference to window size at all.

### 6.4 Drift is not harm

The deployment domain drove max PSI to 3.33 with 5 of 25 features past the effect-size
bound, while aggregate calibration was essentially unchanged (ECE 0.0071 against 0.0060 at
freeze) and discrimination fell only 0.023 (AUROC 0.649 against a frozen 0.672), inside its
declared bound. Large, unambiguous covariate shift; model behaviour intact. A governance
layer wired directly to detection would have escalated a model that was still working.

Relatedly: 22 of 25 features were statistically significant under BH-FDR while only 5
exceeded the effect-size threshold. At deployment sample sizes, significance carries no
information about practical drift.

### 6.5 Separating detection from governance prevents inappropriate escalation (RQ9)

Identical monitor output, two policies, ten windows:

| | separated | collapsed |
|---|---|---|
| windows recommending suspension | **0** | **7** |
| windows in abstention | 5 | 0 |

**H10 is supported.** Note what it supports: *separation*, which is structural and cheap —
not *aggregation*, which is where the framework claims novelty.

### 6.6 Subgroup degradation invisible to aggregate metrics (RQ8)

In the deployment domain, age ΔTPR reached 0.385 against a permutation null band of 0.110 —
real and large — while aggregate calibration stayed within bounds. Race ΔTPR of 0.104
exceeded the specified 0.05 threshold but sat **inside** its null band of 0.128: an alert
indistinguishable from sampling noise. The specified fairness threshold produces both
kinds of error on the same dataset.

The frozen model also breached the fairness bound in-distribution at freeze time
(ΔTPR 0.074), meaning an absolute-threshold monitor contributes a constant non-zero
violation from day one. Behaviour monitors were consequently re-specified to enter the AHS
as change from baseline.

## 7. Statistical analysis

Detection comparisons are bootstrapped over windows (2,000 resamples) and reported with 95%
intervals; none of the integration comparisons excludes zero. Per-feature drift tests are
Benjamini–Hochberg corrected — without it, alert volume measures schema width rather than
data. Subgroup disparities are compared against permutation reference bands under label
exchangeability, and groups are suppressed below both a minimum size and a minimum positive
count, because TPR is conditional on positives and a row-count gate is the wrong instrument.

## 8. Ablation

| Removed | F1 |
|---|---|
| nothing (full) | 0.913 |
| a1_distribution | 0.875 |
| a3_structural | 0.898 |
| calibration | 0.898 |
| fairness | 0.889 |

Every difference is one window wide. **No component is shown to earn its place.** A3 alone
has recall 0 — correct, since the perturbation changes case mix rather than schema.

## 9. Sensitivity

**Thresholds (RQ6).** Precision 1.00 at recall 0.76–0.84 with zero false alarms for bands
0.50–0.75; by band 0.95, precision 0.77 and false-alarm rate 0.70. The specified 0.75 lands
near the knee — a coincidence worth naming as such, since §6.3 shows the same band opening
reviews on clean data at small window sizes.

**Weights (RQ5).** Named configurations span F1 0.840–0.913, so robustness holds in the
moderate regime. But 197 random Dirichlet draws span **0.276–0.936**: a weighting nobody
would notice was bad renders the composite nearly useless, and nothing in the framework
constrains the choice.

**Normalisation (RQ5b).** All three candidate functions reached identical best F1 of 0.913.
The hypothesis that normalisation dominates the weights was **not supported**, and was badly
posed: all candidates are monotone in the raw metric, so below saturation they rank windows
identically and only move where the band must sit. Normalisation matters for *severity
resolution* instead — `threshold_relative` collapses everything past the bound to a single
value, which is why AHS floors at 0.175 and cannot distinguish severity 0.50 from 1.00.

**Missing monitors.** With all seven measured, true AHS on the deployment domain is 0.481.
Treating absent monitors as zero gives 0.677 (overstating health by a full band);
renormalising gives 0.412 (understating it). Both policies are biased, in opposite
directions, and which way is data-dependent. The additive form cannot distinguish
"assumption holds" from "not measured".

## 10. Scalability (RQ7)

Single process, 1 CPU, Python 3.12.3; full package versions in the results JSON.

| Window size | seconds | rows/second |
|---|---|---|
| 1,000 | 0.61 | 1,647 |
| 55,848 | 1.80 | 31,071 |

Peak RSS flat at 365 MB. Full pipeline 1.84 s. A 56× increase in rows costs 3× the
wall-clock; reference size has no measurable effect. Cost is dominated by fixed overhead, so
there is no computational argument for small windows — and §6.3 gives a statistical argument
against them.

## 11. Limitations

1. **RQ2 (detection speed) is unanswered.** D2 has no time axis. This is the single largest
   gap and it is not closable on this substrate.
2. **One dataset, one task, one model, one perturbation family.** The RQ3 replication
   inherits the single-institution limitation of the work it replicates.
3. **Ground truth is injected and binary.** "Degraded" means a perturbation was applied, not
   that the model became clinically unsafe.
4. **35 evaluation windows** is a small sample; the bootstrap is reported so results are not
   read as firmer than they are.
5. **Calibration, fairness and A2 consume labels** a live deployment would not have at
   monitoring time. A2 was additionally run label-blind; the others were not.
6. **A4 is simulated telemetry** and carries no evidential weight whatsoever.
7. **Governance is a simulation with no human in it.** It says nothing about hospital
   behaviour.
8. **Provenance is `MIRROR_UNVERIFIED`.**
9. **No claim of clinical validation, regulatory compliance, or deployment readiness is made
   or supported.** This work sits at the "empirically evaluated on public retrospective
   data" level and no higher.

## 12. Conclusions

The framework's **structural** commitments hold up: a shared versioned registry, monitors
co-located on it, separation of detection from harm assessment from governance, and a
complete audit trail. Separation alone prevented seven of ten inappropriate suspension
recommendations.

The framework's **novel quantitative** commitments do not. Composite scoring produced no
measurable detection advantage over independent detectors; the score is noisy relative to
its own governance bands, biased by window size, saturating above moderate severity,
sensitive to unconstrained weights, and unable to distinguish an assumption holding from an
assumption unmeasured.

The most useful outputs of this project are things the framework does not contain: a
permutation reference band that separates real subgroup disparity from sampling noise; a
window-size rule derived by measuring the score's own noise against its decision bands; the
bracketing analysis showing both missing-monitor policies are biased; and the measured
failure of uncertainty-based OOD detection — including its inversion on the least-represented
patients — on real tabular EHR data.

A composite score is not required to obtain any of these. That is the finding.

## 13. Future work

1. **Acquire D1 (BRFSS)** and run the temporal replay. RQ2 is untouched, and RQ1's negative
   result deserves a second substrate with a genuine time axis before it is generalised.
2. **Test the window-size rule elsewhere.** The method is general; the ~10,000-row constant
   is not.
3. **Label-blind variants of every behaviour monitor**, so real-time detection claims stop
   depending on labels a deployment would not have.
4. **A principled aggregation alternative**, if one is wanted at all: the evidence here
   suggests reporting monitors separately with per-monitor reference bands, and reserving
   escalation for corroborated harm, would be both simpler and better supported.
5. **Verified provenance** before any of it is published.
