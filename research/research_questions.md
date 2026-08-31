# HAVM — Research Questions (Stage 0)

Each question below states: the measurable outcome, the comparator, and **the result that would count against HAVM**. A question with no disconfirming outcome is not a research question and has been rewritten or dropped.

## 0. Provenance of the questions

| Source | RQs |
|--------|-----|
| P-NEW §6.1 (paper-stated, falsifiable as written) | RQ1, RQ2, RQ3, RQ8*, RQ9* |
| BRIEF §45 | RQ1–RQ9 |
| Added here (gap in both) | **RQ5b normalisation sensitivity**, **RQ0 ground truth** |

\* P-NEW's RQ4 (clinician workload, NASA-TLX) and RQ5 (governed adaptation safety) map onto BRIEF RQ9 and BRIEF §50 respectively. P-NEW RQ4 requires human subjects and is **out of scope** — see `scope.md` §3.

---

## RQ0 — Ground truth *(prerequisite, not optional)*

**Question.** What operational definition of "clinically meaningful degradation" makes alert precision and recall measurable at all?

Neither paper defines this, and every other RQ is unmeasurable without it. Proposed pre-registered definition, fixed **before** any monitoring run:

> A degradation episode exists in window *t* if, on labels for that window, a pre-declared performance functional falls below a bound declared in the Assumption Registry at model-freeze time — e.g. AUROC drop ≥ δ from the frozen validation value, **or** worst-subgroup TPR drop ≥ δ_g, **or** ECE above the declared bound — sustained over ≥ k consecutive windows.

Three consequences to state plainly:
- Ground truth is **label-dependent** and therefore only available retrospectively. Monitors that use labels (A2, fairness) are partly evaluated against a quantity derived from the same labels. Any A2/fairness monitor must be scored on a *label-blind* variant, or on delayed labels, or the comparison is circular.
- δ, δ_g and k are policy choices, not facts. Report results across a grid of them.
- For injected perturbations, onset time is known exactly; for real events it is not. Detection-delay results must separate the two.

**Disconfirming outcome:** if precision/recall rankings between monitoring configurations flip across reasonable choices of δ and k, then no configuration is better than another and every downstream RQ result is an artefact of the ground-truth definition. That finding is worth reporting on its own.

---

## RQ1 — Does integration improve alert precision?
*(BRIEF RQ1; P-NEW RQ1)*

**Outcome:** positive predictive value of alerts against RQ0 ground truth, at matched recall.
**Comparators:** BRIEF §20 ladder — no monitoring · single drift monitor · drift+calibration · drift+OOD · drift+fairness · all monitors alarming independently (OR-rule) · AHS-triggered.
**Method:** precision–recall over the replay; bootstrap over windows for CIs; matched-recall comparison, not matched-threshold (otherwise the comparison measures threshold choice, not integration).
**Counts against HAVM:** AHS raises alert volume without improving PPV at matched recall; or the independent OR-rule matches AHS. P-NEW states this outcome explicitly as counting against the co-location principle.

## RQ2 — Does it detect earlier?
*(BRIEF RQ2; P-NEW RQ2)*

**Outcome:** windows elapsed between episode onset and first sustained alert.
**Comparators:** continuous monitoring vs simulated periodic revalidation (monthly / quarterly / annual cadence over the replay).
**Counts against HAVM:** detection interval no shorter than periodic revalidation once alert budget is held equal. Note the trap: continuous monitoring can always "detect earlier" by alarming constantly. Delay must be reported *jointly* with false-alarm rate, never alone.

## RQ3 — Modality transfer
*(BRIEF RQ3; P-NEW RQ3 — the replication question)*

**Outcome:** relative ranking of shift/OOD detectors on tabular EHR vs their published ranking on general benchmarks.
**Comparators:** Rabanser et al.'s two-sample-testing-on-representations, MMD, PSI, per-feature KS with FDR control, Mahalanobis/kNN distance in model representation space, isolation forest, and (only if a neural arm exists) an energy score.
**Prior:** Ulmer et al. [21] predicts non-transfer.
**Counts against HAVM's second design principle:** rankings *do* transfer, in which case modality-specific validation is less necessary than P-NEW argues. Either result is publishable.
**Note:** the energy score presupposes a logit-producing classifier. With a gradient-boosted monitored model it is not mathematically meaningful. It is implemented only if a neural arm is added — otherwise this is reported as a scope decision, not silently skipped.

## RQ4 — AHS validity
*(BRIEF RQ4)*

**Outcome:** correlation (Spearman, plus lagged cross-correlation) between AHS(t) and measured degradation; and whether AHS decreases monotonically with increasing injected violation severity.
**Comparator:** best single normalised violation signal.
**Counts against HAVM:** AHS correlates no better than its best single component — i.e. aggregation adds nothing but opacity. Also disconfirming: AHS non-monotone in severity within the controlled regime, which would mean the composite is not measuring what it claims.

## RQ5 — Weight sensitivity
*(BRIEF RQ5)*

**Outcome:** variance in precision, recall and detection delay across weight configurations (equal · risk-weighted · severity-weighted · random Dirichlet draws).
**Counts against HAVM:** detection performance swings materially with weights, meaning AHS reports the analyst's priors rather than the data.
**Specific sub-question from `paper_analysis.md` §5:** can a maximal violation on a low-weight monitor be made invisible to the governance bands? If yes, quantify the masking region — the set of (w, v) where a full violation cannot cross the review threshold.

## RQ5b — Normalisation sensitivity *(added; not in BRIEF or either paper)*

**Question.** How much of AHS's behaviour is determined by the choice of squashing function mapping raw metrics to vₖ ∈ [0,1], rather than by the weights?

**Outcome:** same detection metrics as RQ5, varied over linear-clip / threshold-relative / log / logistic / empirical-quantile normalisations, weights held fixed.
**Why it matters:** the weights are bounded and sum to 1; the normalisation is unbounded in effect and undocumented anywhere. My prior is that it dominates. If so, the field's focus on weighting schemes is misplaced — a genuine contribution.

## RQ6 — Threshold sensitivity
*(BRIEF RQ6)*

**Outcome:** precision, recall, alert volume and detection delay across AHS bands (0.50–0.90) and per-monitor thresholds.
**Reported as:** trade-off curves, plus an alert-burden proxy (alerts per monitoring period per model).
**Counts against HAVM:** no threshold region achieves usable precision at tolerable alert volume — i.e. the framework is unoperable at any setting, not merely mis-tuned.

## RQ7 — Scalability
*(BRIEF RQ7)*

**Outcome:** wall-clock, peak memory, storage and throughput at 10/25/50/75/100% of cohort and across window sizes.
**Reported as:** measured curves with fitted complexity, on stated hardware. No claim of scalability without measurement.

## RQ8 — Subgroup degradation invisible to aggregates
*(BRIEF RQ8)*

**Outcome:** episodes where worst-subgroup performance degrades beyond the parity bound while aggregate AUROC stays within its bound — counted, and checked for whether any monitor flags them.
**Grounding:** this is the one place where the corpus gives a strong prior — Yang, Y. et al. [25] (E3) shows fairness properties failing to transfer under distribution change.
**Counts against HAVM:** no such episodes occur in the replay (fairness monitoring adds nothing here), or they occur but the fairness monitor misses them at any usable threshold.
**Caveat to carry into the write-up:** MIMIC-IV race/ethnicity is coarse and self-reported; small subgroups give unstable per-group rates. Report per-group n and CIs, and pre-declare a minimum group size below which no fairness claim is made.

## RQ9 — Does separating detection from governance help?
*(BRIEF RQ9)*

**Honest statement of a limitation:** with no human in the loop and no real institution, this cannot be answered empirically. What *can* be done is a **simulation**: implement Table 7's separation (detect → judge harm → govern → act), plus a collapsed variant where detection triggers action directly, and count inappropriate automated escalations under identical monitor outputs.

**Outcome:** escalation counts, state-occupancy time, recovery time, false-escalation rate.
**What this is not:** evidence about hospital governance. It is a mechanism study of the policy layer. It will be labelled a simulation everywhere it appears, per BRIEF §32.

---

## Prioritisation

Given finite resources, in order:

**Tier 1 (must deliver):** RQ0, RQ4, RQ5, RQ5b, RQ6 — all runnable once one replay pipeline exists; none depends on the integration hypothesis being true.
**Tier 2 (core scientific claim):** RQ1, RQ2, RQ8.
**Tier 3 (if resources allow):** RQ3 (needs several detector implementations), RQ7 (needs full-scale runs), RQ9 (cheap but lowest evidential weight).
**Dropped:** P-NEW RQ4 (clinician cognitive load) — requires human subjects and ethics approval; documented as a deliberate scope boundary, and named as the gap the capstone does *not* close.
