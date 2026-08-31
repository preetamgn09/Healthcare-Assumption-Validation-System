# Gate 3 — Stage Report (BRIEF §65)

## 1. What was implemented

A verified, versioned, leakage-tested data pipeline for D2; a schema contract fitted on
training data; three prediction baselines; selection and freezing of one model; and
version 0.1 of the assumption registry. One experiment, EXP001, reproducible from a single
command.

## 2. Files created

| Path | Purpose |
|------|---------|
| `configs/d2_diabetes.yaml` | Every cohort, label, domain, split, feature, subgroup and threshold decision |
| `src/havm/utils.py` | Config loading, hashing, environment/reproducibility record |
| `src/havm/datasets/d2.py` | Verify → cohort → label → domain split → patient-grouped split |
| `src/havm/features.py` | ICD-9 grouping (Strack et al. Table 2), specialty vocabulary |
| `src/havm/schema.py` | Schema contract fit + violation detection (A3 seed) |
| `src/havm/metrics.py` | AUROC, AUPRC, Brier, ECE with bin detail, subgroup rates |
| `src/havm/models.py` | Prevalence / logistic / gradient-boosting baselines |
| `src/havm/registry.py` | L2 assumption registry with provenance tagging |
| `scripts/fetch_d2.py` | Acquisition with checksum enforcement |
| `scripts/run_g3.py` | EXP001 runner |
| `tests/` | 31 tests: analytic metrics, leakage, determinism, schema, ICD-9 |
| `research/experiment_log.md` | EXP001 record |
| `README.md`, `requirements.txt`, `.gitignore` | — |

**Files modified:** none — this is the first code gate.

## 3. Tests executed

`python -m pytest tests/ -q` → **31 passed**, no warnings, ~4 s.

Coverage of what matters:
- **Analytic (BRIEF §38):** perfectly calibrated predictions → ECE < 0.01 on 200k samples;
  systematic overconfidence → ECE > 0.05; ECE bounded in [0,1]; maximally wrong predictions
  → ECE = 1.0 exactly; TPR/FPR/precision exact on a hand-computed example.
- **Leakage:** train/validation patient-disjoint; the domain-defining column is not a model
  feature; excluded discharges absent from all three sets; domains correctly and disjointly
  assigned.
- **Determinism:** two independent runs produce identical row ordering in every split.
- **Schema:** validates its own training data; detects unseen categories, missing columns
  and out-of-range values.
- **Regression:** the `None`-as-NaN trap cannot silently return.

## 4. Results

Source-domain validation, n = 9,108, prevalence 0.1073:

| Model | AUROC | AUPRC | Brier | ECE |
|-------|-------|-------|-------|-----|
| Prevalence baseline | 0.5000 | 0.1073 | 0.0958 | 0.0016 |
| Logistic regression | 0.6606 | 0.2077 | 0.0921 | 0.0080 |
| **Gradient boosting (frozen)** | **0.6720** | **0.2256** | **0.0910** | **0.0060** |

Consistent with the published range for this task and dataset. The model only has to be a
credible monitoring subject; it is not the contribution.

## 5. Scientific assumptions made

1. **The ER / non-ER split is a meaningful distribution shift.** Taken from the published
   shift literature on this dataset rather than invented here, but it is a *domain* shift,
   not a *temporal* one — no detection-delay result can come from D2.
2. **30-day readmission, positive class = `<30`.** `>30` and `NO` are both negatives; the
   alternative (restricting to readmitted patients only) answers a different question.
3. **Expired and hospice discharges are excluded** because readmission is undefined for them.
   This removes 2,423 encounters and makes the cohort survivorship-conditioned.
4. **Missing values are informative.** `?` becomes an explicit `Unknown` category rather
   than being imputed or dropped, so missingness stays visible to fairness and A3 monitoring.
5. **Patients may appear in both training and deployment domains** (4,679 do). Kept, because
   people genuinely return through the ED; excluding them would bias the deployment
   population by removing the highest-risk patients. A config flag runs the sensitivity case.
6. **The top-decile operating point is a workload anchor, not an optimum.** POLICY, to be
   varied in Gate 6.

## 6. Engineering assumptions

1. `keep_default_na=False` on load, so `None` stays a category.
2. Admin ID columns treated as categorical, not numeric — they are identifiers.
3. Specialty vocabulary is fitted on training only; a new specialty at deployment is a
   detectable A3 event, not a silent remap.
4. sklearn only — no LightGBM/XGBoost until a measured need justifies the dependency.
5. Model artefact is joblib, hashed and recorded; it is not committed to Git.

## 7. Known limitations

1. **Provenance is `MIRROR_UNVERIFIED`.** UCI was unreachable from the build environment.
   Metadata matches the published dataset exactly and the checksum is recorded, but this
   must be re-fetched from UCI before any result is reported.
2. **No temporal axis.** D2 cannot carry Experiments 1, 2 or 11. D1 (BRFSS) must land for
   those, and it has not been downloaded.
3. **Small subgroups are suppressed.** Asian, Hispanic and Other fall below the declared
   minimum of 200 in validation. Fairness conclusions will be confined to two race groups
   on this substrate — a real limitation of D2, not of the method.
4. **Source domain is smaller than the deployment domain** (36.6k vs 55.8k encounters).
   Realistic, but it means training data is the scarcer resource.
5. **The registry's thresholds and weights are placeholders** with no evidential status.
6. **A2 and OOD are not implemented**, by plan.

## 8. Computational cost

~35 s end to end, single CPU process, < 1 GB RAM. Raw data 19 MB. No GPU. Nothing here
needs optimisation; the first real cost will be MMD in Gate 4, where a linear-time
estimator is already planned.

## 9. Recommended next stage

**Gate 4 — monitors.** Implement A1 (distributional), A3 (structural, already seeded by the
schema contract), calibration and fairness, all reading their configuration from the
registry, all with analytic tests. Run them on the still-sealed deployment domain only as a
*single* comparison, not as a replay, so the seal is broken once and deliberately.

In parallel: download BRFSS so D1 exists before Gate 5, since the temporal replay is the
centrepiece experiment and D2 cannot supply it.
