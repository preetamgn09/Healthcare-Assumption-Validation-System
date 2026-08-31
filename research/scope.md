# HAVM — Scope, Dataset Strategy and Roadmap (Stage 0)

Every dataset figure below is **to be verified against the provider's own documentation at access time** and recorded in `research/dataset_selection.md` (Stage 1). Nothing here has been downloaded or measured.

---

## 1. Evidence classes used throughout the project (BRIEF §33)

Every number this project ever emits carries one of these tags, in the filename, the table caption and the registry:

| Tag | Meaning |
|-----|---------|
| `OBSERVED` | Measured from real healthcare data as it came |
| `INJECTED` | Real data with a controlled perturbation applied |
| `SIMULATED` | Operational/infrastructure events with no real counterpart in the data |
| `POLICY` | A threshold, weight or governance rule chosen by us |
| `CONCLUSION` | A claim supported by experiments in this project |

A1–A4, AHS, all weights and all thresholds start life as `POLICY` (see `paper_analysis.md` §0).

## 2. In scope

- **L2 Assumption Registry** — versioned, machine-readable, single source of every threshold and weight. Highest-value component: it is the one thing both papers argue for (static documentation lapses silently, [9,17]) that requires no unavailable evidence to justify.
- **L3 monitors:** A1 distributional, A2 relational, A3 structural, A4 operational (`SIMULATED`), calibration, OOD, fairness.
- **AHS** with explicit, inspectable decomposition and full component history.
- **Triage / harm assessment** as a separate stage from detection — following P-NEW's use of Rabanser et al.'s detect-vs-harmful distinction.
- **Governance state machine + audit trail**, as `SIMULATED` policy.
- **Replay engine** — one implementation serving both historical replay and simulated streaming (BRIEF §31).
- **Baseline ladder and all sensitivity experiments.**

## 3. Out of scope (deliberate boundaries, to be stated in the final report)

| Excluded | Why |
|----------|-----|
| Clinical knowledge consistency (ABA+G, clinical NLI) | BRIEF §51; the two papers in this domain do not interoperate with statistical pipelines, and building an NLP subsystem would consume the whole budget. Documented as the gap we do **not** close. |
| Human-factors evaluation (P-NEW RQ4, NASA-TLX) | Human subjects, ethics approval, clinicians. Named as Gap 3, left open. |
| Live or prospective deployment | Nothing in this project reaches E4. |
| Federated / multi-institution validation (Gap 7) | Requires partner institutions. |
| Medical imaging | Modality mismatch with the monitored task; imaging OOD findings [12] explicitly do not transfer to tabular. |
| Real infrastructure telemetry | Not present in any public dataset. A4 is simulated and labelled. |
| Any regulatory, safety or clinical-validation claim | Unsupported by construction. |

## 4. Dataset strategy (Q9)

### Candidates

**MIMIC-IV — recommended primary.**
Longitudinal, hospital + ICU + ED modules, large enough for subgroup work, and the reference substrate in both papers [13].
- *Access:* PhysioNet credentialed access — CITI "Data or Specimens Only Research" training certificate, credentialing application, signed DUA. **Lead time is days to weeks and is the single largest schedule risk.** Start on day one of Stage 1.
- *Critical caveat that shapes the entire temporal design:* MIMIC-IV date-shifts each patient independently into the future for de-identification. Absolute admission dates are **not real calendar dates**. Real-time information survives only as a coarse per-patient band (`anchor_year_group`, three-year buckets). **Consequence:** true calendar-time replay at daily or weekly resolution is not possible; the temporal split must be constructed on the de-identification-preserved band, and "windows" within a band are cohort-ordered, not calendar-ordered. This must be verified against the release notes in Stage 1, and if confirmed it is a limitation to state in the abstract of any write-up, not a footnote.
- *Real degradation event available:* the ICD-9 → ICD-10 transition is visible in the diagnosis tables via an explicit code-version field. If diagnosis-derived features are used, this is a genuine `OBSERVED` structural/coding change — exactly what BRIEF §22 asks for and rare in public data. Verify presence and distribution before committing to it.

**EHRSHOT — considered, recommended as secondary at most.**
Non-ICU-restricted, hence closer to a general deployment population, with a released foundation model [23]. But **6,739 patients** is small: after cohorting and windowing, per-subgroup counts will be too thin for stable fairness estimates, which is the point of RQ8. Also requires a research DUA. Good for RQ3 modality-transfer replication on a second substrate; poor as the primary.

**eICU-CRD — recommended secondary for RQ-generalisation.**
Multi-hospital ICU data. Its value is orthogonal: it supports **cross-site** shift where MIMIC-IV supports temporal shift, which is the better test of whether the framework generalises when thresholds don't (BRIEF §29). Same PhysioNet credentialing, so it comes free once MIMIC-IV access exists.

**Diabetes 130-US Hospitals (UCI) — recommended open development substrate.**
~100k encounters across 130 hospitals over a decade, with a readmission label and demographic attributes; **openly downloadable, no DUA**. Not a substitute for MIMIC-IV as evidence — it is coarse and encounter-level — but it lets Stages 3–13 be built, tested and debugged *while credentialing is pending*, on real (not synthetic) healthcare data. This is the schedule de-risker.

**MIMIC-IV demo (open, ~100 patients)** — smoke tests only (BRIEF §40 Level 1).

### Recommendation

| Role | Dataset |
|------|---------|
| Smoke tests (L1) | MIMIC-IV demo |
| Development substrate while credentialing pends | Diabetes 130-US |
| **Primary evidence — temporal replay** | **MIMIC-IV** |
| Generalisation — cross-site | eICU-CRD |
| Generalisation — second EHR substrate (if budget allows) | EHRSHOT |

Selection is on longitudinal structure, subgroup power and shift opportunity — **not** on which produces the nicest curves (BRIEF §17). If MIMIC-IV access fails entirely, the fallback is Diabetes 130-US as primary with the loss of statistical power and clinical granularity stated as a headline limitation, not buried.

## 5. Prediction task (Q10)

**Recommended: in-hospital mortality predicted from the first 24 hours of an admission.**

| Criterion | Why this task |
|-----------|---------------|
| Label availability | Directly derivable, unambiguous, no adjudication |
| Prevalence | Roughly 8–12% in ICU cohorts — imbalanced enough to make calibration and AUPRC meaningful, common enough for stable subgroup estimates |
| Temporal shift | Case-mix, coding and care-process changes over the covered span plausibly move both P(X) and P(Y\|X) |
| Fairness | Subgroup attributes present (age band, sex, insurance, and coarse self-reported race/ethnicity) |
| Calibration | A probability output that is genuinely interpretable, so ECE means something |
| Feasibility | Well-trodden feature extraction; runs on a laptop |

Rejected: **readmission** (definition-sensitive, index-event leakage traps, and its own literature of methodological disputes — a distraction from the monitoring question); **length of stay** (regression complicates calibration, fairness and OOD framing simultaneously).

**The prediction model is the object being monitored, not the contribution.** Baselines: majority/prevalence → logistic regression with regularisation → gradient boosting (LightGBM). The best-validating classical model is frozen and never retrained during the primary experiment (BRIEF §49). No deep learning unless a neural arm is explicitly added for the energy-OOD comparison in RQ3 — and if it is, it is added *as an experiment*, not as an upgrade.

## 6. Which monitors are genuinely evaluable, and which are simulated (Q11, Q12)

| Monitor | Evidence class | Notes |
|---------|---------------|-------|
| A1 distributional | `OBSERVED` | Real. Needs FDR control across features × windows or the alert counts are meaningless. |
| A2 relational | `OBSERVED`, with a caveat | Labels exist retrospectively but not at deployment time. Must be run under a declared label-delay to be honest; otherwise it is an oracle, not a monitor. |
| A3 structural | Mostly `OBSERVED` | Genuine substrate: ICD-9/10 code-system change, missingness pattern shifts, item vocabulary changes. Schema removals are `INJECTED`. |
| A4 operational | `SIMULATED` — always | No public dataset carries pipeline telemetry. Replay layer injects missing/delayed batches, latency, version changes. Never described as deployment evidence. |
| Calibration | `OBSERVED` | ECE, reliability curves, Brier; temperature scaling as the recalibration action. |
| Uncertainty | `OBSERVED`, modest | For a GBM: ensemble variance / quantile spread. No Bayesian deep learning (BRIEF §6). |
| OOD | `OBSERVED` + `INJECTED` | Tabular-appropriate detectors first; energy only with a neural arm. Ulmer et al. predicts they underperform — that prediction is the experiment. |
| Fairness | `OBSERVED` | Per-group TPR/FPR/calibration with minimum-group-size gating and CIs. |
| Knowledge consistency | — | Out of scope. |

## 7. Minimum viable vs ambitious (Q15, Q16)

**MVP — the thing that must exist for the capstone to be defensible:**
Registry → frozen model → replay on one real dataset → A1 + A3 + calibration + fairness → AHS with full decomposition → governance states + audit → baseline ladder → RQ0/RQ4/RQ5/RQ5b/RQ6 → reproducible from one command.

**Ambitious — added only after MVP passes:**
A2 with label delay, OOD detector bake-off (RQ3), second and third datasets (RQ7/generalisation), scalability curves, streaming mode, adaptation experiment (recalibrate vs retrain vs no action), dashboard and API.

The dashboard is last. It demonstrates nothing scientific and consumes disproportionate time.

## 8. Risks

### 8.1 Data access (Q18)
- **Credentialing latency** — highest-probability schedule risk. Mitigation: start immediately; build on Diabetes 130-US in parallel.
- **Date obfuscation in MIMIC-IV** — may cap temporal resolution at three-year bands. Mitigation: design the replay engine so window construction is a config-level choice, not an assumption baked into the monitors.
- **Licensing** — no patient-level data in Git, ever; no data in logs, dashboards, error messages or experiment artefacts (BRIEF §53).

### 8.2 Compute (Q17)
Raw MIMIC-IV is tens of GB compressed; cohort extraction is the memory-heavy step, monitoring itself is cheap except for MMD (naïve kernel MMD is O(n²) — use a linear-time estimator or subsampling with a measured error budget). Everything else is vectorisable. Mitigation: Parquet + chunked extraction; the four-level test ladder in BRIEF §40; estimate before running anything expensive (BRIEF §68). No distributed computing.

### 8.3 Scientific validity (Q19) — the serious ones

1. **Ground truth is a construct, not an observation** (RQ0). Every precision/recall number inherits the choice of δ and k. Mitigation: pre-register, then report over a grid; if rankings flip, that *is* the result.
2. **Circularity in A2/fairness evaluation** — monitors that consume labels being scored against label-derived ground truth. Mitigation: label-blind variants and delayed labels.
3. **Multiple comparisons** — hundreds of tests per window inflate alert counts mechanically. Mitigation: FDR control, declared in the registry, applied identically across all baselines.
4. **Injected-perturbation circularity** — a perturbation designed to be visible to a monitor will be detected by it. This proves the monitor is wired up, not that it is useful. Mitigation: perturbations must be specified by their *effect on the data-generating process*, not by the statistic they move; report `OBSERVED` and `INJECTED` results separately and never pool them.
5. **Correlated monitors** — A1 and OOD respond to the same underlying change; AHS double-counts it. Mitigation: measure inter-monitor correlation and report it alongside every ablation.
6. **Single-dataset, single-seed conclusions** — mitigation: bootstrap over replay windows, multiple seeds, CIs on every headline number.
7. **Confirmation pressure** — the framework is the author's own. Mitigation: the negative results are preserved and reported by default (BRIEF §66); a pre-registered analysis plan is written before the primary experiment runs.

## 9. Roadmap (Q20)

Consolidates BRIEF §64's 21 stages into eight gates. Each ends with the §65 report and a stop.

| Gate | Content | BRIEF stages | Gating condition |
|------|---------|--------------|------------------|
| **G0** | This analysis; provenance decision on §0; pre-registered ground-truth definition | 0 | Your approval + open items in `paper_analysis.md` §7 resolved |
| **G1** | Dataset investigation; credentialing started; `dataset_selection.md`; task and cohort definition fixed | 1 | Access path confirmed for at least one real dataset |
| **G2** | Architecture + registry schema + evidence-tagging conventions | 2, 10 | Registry can express every threshold and weight the experiments need |
| **G3** | Data pipeline, temporal split, dataset versioning; model baselines trained, evaluated, **frozen** | 3, 4 | Frozen model card recorded in the registry |
| **G4** | Monitors: A1, A3, calibration, fairness — with the analytic tests of BRIEF §38 | 5, 6, 7, 9 | Mathematical tests pass (P=Q ⇒ MMD→0, perfect calibration ⇒ ECE→0, etc.) |
| **G5** | AHS + triage + governance + audit; end-to-end replay | 11, 12, 13 | AHS fully decomposable; every alert reconstructible from the audit log |
| **G6** | Baselines, controlled violations, ablation, threshold/weight/normalisation sensitivity | 14–17 | Tier-1 RQs answered, negative results included |
| **G7** | A2 with label delay, OOD bake-off, scalability, second dataset | 8, 18, 19 | Budget permitting |
| **G8** | Dashboard/API, final reproducibility pipeline, report evidence pack | 20, 21 | One command reproduces every figure |

Nothing proceeds past a gate without your approval.
