# HAVM — Implementation Hypotheses (Stage 0)

Each hypothesis states a prediction, the test, and **the observation that would falsify it**. Hypotheses without a falsifier are not listed. Per BRIEF §3, none of these is assumed true; several I expect to fail, and where I have a prior I state it.

Conventions: `OBSERVED` / `INJECTED` / `SIMULATED` / `POLICY` as defined in `scope.md` §1. Ground truth as defined in `research_questions.md` RQ0. All results reported with bootstrap CIs over replay windows.

---

## Tier A — Correctness (must hold, or the implementation is wrong)

These are not research findings. They are the analytic tests of BRIEF §38, and failure means a bug, not a discovery.

| ID | Prediction | Falsifier |
|----|-----------|-----------|
| **A1** | With deployment data drawn from the training distribution, MMD → 0, PSI → 0, per-feature tests reject at ≈ the nominal rate after FDR control | Systematic non-zero drift signal on identically distributed data |
| **A2** | Perfectly calibrated synthetic predictions ⇒ ECE → 0; miscalibrated ⇒ ECE > 0 and temperature scaling reduces it | ECE insensitive to known miscalibration |
| **A3** | All violation signals zero ⇒ AHS = 1; any vₖ increases with others fixed ⇒ AHS strictly decreases | AHS non-monotone in a single component |
| **A4** | Σwₖ = 1 and vₖ ∈ [0,1] ⇒ AHS ∈ [0,1] with no clipping needed | AHS leaves [0,1] |
| **A5** | Every alert is reconstructible from the audit log alone — raw metric, normalised value, threshold, registry version, weights, AHS, state transition | Any alert that cannot be reproduced from stored records |
| **A6** | Changing a threshold in the registry changes monitor behaviour with no code edit | Any hardcoded threshold or weight found in `src/` |

## Tier B — Core scientific hypotheses

### H1 — Integration improves alert precision
**Prediction.** At matched recall against RQ0 ground truth, AHS-triggered alerting achieves higher PPV than the best single detector and than independent detectors combined by an OR-rule.
**Test.** BRIEF §20 baseline ladder over the full replay; matched-recall comparison; bootstrap CIs; `OBSERVED` and `INJECTED` reported separately.
**Falsifier.** No PPV improvement at matched recall, or improvement inside the CI of the OR-rule baseline.
**Prior.** Genuinely uncertain, and the framing matters: P-OLD treats this as established, P-NEW as open (`paper_analysis.md` D5). I expect any gain to be **small and threshold-dependent**, because the monitors are correlated (H6) and because the OR-rule baseline is stronger than the literature's framing implies.

### H2 — Continuous monitoring detects earlier than periodic revalidation
**Prediction.** Median detection delay is shorter than simulated monthly/quarterly revalidation at equal false-alarm budget.
**Falsifier.** No delay advantage once alert volume is held equal; or an advantage that disappears when detection delay is measured only on `OBSERVED` episodes.
**Prior.** Likely true but close to trivially so, and easily overstated. The interesting number is the delay-vs-false-alarm frontier, not the delay alone.

### H3 — AHS decreases monotonically with injected violation severity
**Prediction.** Within a controlled regime, AHS is monotone decreasing in perturbation magnitude for each of A1, A2, A3, A4, OOD, calibration and fairness taken singly.
**Falsifier.** Non-monotonicity, or **saturation** — a regime where increasing severity no longer moves AHS because Σwₖvₖ has floored the score. I expect saturation to be found, and expect it to be a reportable limitation of the additive form rather than a bug.

### H4 — AHS is robust to moderate weight variation
**Prediction.** Precision, recall and detection delay vary less across weight configurations than across threshold settings.
**Test.** RQ5 grid plus random Dirichlet draws; report variance decomposition.
**Falsifier.** Weight-induced variance comparable to or exceeding threshold-induced variance — which would mean AHS mostly reports the analyst's priors.
**Prior.** I expect **H4 to survive against weights and fail against normalisation** (see H5).

### H5 — Normalisation choice dominates weight choice *(the added hypothesis)*
**Prediction.** Varying the squashing function vₖ (linear-clip / threshold-relative / log / logistic / empirical-quantile) with weights fixed produces larger swings in detection performance than varying the weights with normalisation fixed.
**Falsifier.** Normalisation-induced variance ≤ weight-induced variance.
**Why it is worth running.** Neither paper nor the BRIEF specifies the normalisation, while the BRIEF devotes a whole section (§11) to weights. If the unspecified free parameter turns out to be the influential one, that is a finding about composite health scores generally, not just about HAVM — and it is cheap to obtain.

### H6 — Monitors are correlated, and AHS double-counts
**Prediction.** A1 drift and OOD-exposure signals are substantially correlated across the replay, so their joint contribution to AHS exceeds their joint information content.
**Test.** Inter-monitor correlation matrix over windows; ablation with and without each; comparison of AHS against a decorrelated aggregate.
**Falsifier.** Low inter-monitor correlation, in which case additive aggregation is better justified than I expect.

### H7 — Fairness and calibration signals catch degradation the drift monitors miss
**Prediction.** There exist replay windows with worst-subgroup degradation or calibration drift beyond declared bounds while A1 signals stay below threshold.
**Test.** RQ8 episode counting with minimum-group-size gating.
**Falsifier.** Every such episode is already flagged by distribution monitoring — i.e. the extra monitors are redundant on this data. Reporting that would count directly against the co-location principle.
**Prior.** Expected to hold, because Yang, Y. et al. [25] (E3 clinical) shows fairness properties failing to transfer under distribution change — the strongest prior available anywhere in the corpus.

### H8 — Detector rankings do not transfer from general benchmarks to tabular EHR
**Prediction.** Rank correlation between published general-benchmark ordering and measured tabular-EHR ordering is weak; representation-based two-sample testing loses its advantage; uncertainty-based OOD underperforms.
**Falsifier.** Rankings hold, which would weaken P-NEW's second design principle (modality-specific validation).
**Prior.** Non-transfer, following Ulmer et al. [21] — this is a replication attempt in a new direction, and either outcome is worth reporting.

### H9 — A low-weight monitor can hide a maximal violation
**Prediction.** For a monitor with weight w, a violation of vₖ = 1 moves AHS by at most w; if w < (1 − review threshold), a total violation of that assumption cannot by itself trigger review.
**Test.** Analytic derivation, then empirical confirmation with an injected total violation on the lowest-weighted monitor.
**Falsifier.** Governance triggers anyway, which would mean the triage layer is not in fact driven by AHS alone.
**Note.** This one is close to provable by inspection. Its value is in **quantifying the masking region** across the weight configurations under study, and in showing whether any plausible weighting leaves a whole assumption class effectively unmonitored. If so, the honest conclusion is that AHS should never be the sole trigger — the per-monitor thresholds must remain live in parallel, which is a design recommendation the papers do not make.

### H10 — Separating detection from governance reduces inappropriate automated escalation
**Prediction.** In `SIMULATED` governance, inserting the harm-assessment stage between detection and action reduces escalations to suspension under identical monitor outputs.
**Falsifier.** No reduction, or a reduction achieved only by also missing real degradation episodes.
**Standing caveat.** This is a mechanism study of a policy layer with no human in it. It is not evidence about hospital governance and will never be described as such.

---

## What a negative overall result looks like, and why it is acceptable

If H1 fails, H3 saturates, H5 holds and H9 quantifies a large masking region, the project's conclusion is:

> Composite assumption scoring, as specified, did not improve alert precision over independent detectors on this substrate; its behaviour was dominated by an unspecified normalisation choice; and it can structurally conceal a total violation of a low-weighted assumption. Co-location of monitors on a shared registry retains value for auditability and reproducibility, independent of any aggregation benefit.

That is a **complete and publishable capstone**, and it satisfies BRIEF §70's success criteria — every one of which is about demonstrating capability and measurement, not about HAVM being correct. It is worth saying now, before any code exists, that this outcome is planned for rather than feared.
