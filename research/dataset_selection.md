# HAVM — Dataset Selection (Stage 1)

**Constraint set by you:** no credentialed access. That removes MIMIC-IV, eICU-CRD and EHRSHOT (all require CITI training, a credentialing application and a signed DUA), and it removes them permanently unless you change your mind — so this document selects from **openly licensed data only**.

Nothing has been downloaded. This container's network is restricted to package repositories (PyPI, GitHub, npm, Ubuntu); `cdc.gov` and `archive.ics.uci.edu` are **not reachable from here**. Acquisition happens on your machine, or by uploading the files into a session. Exact commands are in §7.

---

## 1. What this costs, stated plainly

BRIEF §16 says the project must use real-world healthcare data, and §17 says a dataset must not be swapped merely because another is easier. The constraint is legitimate — credentialing latency was flagged in Stage 0 as the largest schedule risk — but it has three scientific consequences that belong in the final report's limitations, not in a footnote:

1. **The review's own substrates are gone.** Both papers anchor the ingestion and benchmarking layers to MIMIC-IV and EHRSHOT. Results here speak to *tabular health data*, not to *ICU-scale longitudinal EHR*.
2. **RQ3 is weakened, not lost.** Ulmer et al.'s negative result — the one clinical data point in the whole corpus — is specifically about *tabular EHR*. Replicating it needs an EHR-derived substrate. One of the two datasets below is a genuine EHR extract, which preserves most of the question.
3. **No single open dataset has both real timestamps and real EHR provenance.** That is the binding fact of this stage. The recommendation below uses two datasets, each supplying what the other lacks, and never pools them.

An optional upgrade path stays open at zero cost to the current plan: PhysioNet credentialing can be started at any time in the background, and if it lands, MIMIC-IV becomes a third substrate for RQ-generalisation. Nothing in the design below has to change if it does. I am not pressing for it.

## 2. Candidates evaluated

Assessed against the BRIEF §17 dimensions. Every figure is cited to a primary source; anything I could not verify is marked **[verify]** and must be confirmed at download time before it enters the report.

### C1 — BRFSS (CDC Behavioral Risk Factor Surveillance System) ✅ recommended: temporal substrate

| Dimension | Assessment |
|-----------|-----------|
| Relevance | Population health risk data; the monitored model is a chronic-disease risk stratifier — a plausible deployed-AI use case, though not a hospital EHR model |
| Size | ~400,000–490,000 records **per year**; e.g. 491,773 (2013), 486,303 (2016), 450,016 (2017), 438,693 (2021), 401,958 (2020) |
| Modality | Mixed-type tabular (categorical, ordinal, count, derived) — the modality Ulmer et al. concerns |
| Longitudinal structure | Repeated cross-section, annually since 1984, **with `IDATE` / `IMONTH` / `IDAY` / `IYEAR` per record** — so replay windows can be **monthly**, giving ~120 windows over a decade rather than ~10 |
| Target task | Cardiovascular risk (`_MICHD`) recommended; diabetes (`DIABETE3`/`DIABETE4`) as alternate |
| Shift opportunities | **Exceptional, and documented by the data owner.** The 2011 switch to raking (iterative proportional fitting) plus the addition of cell-phone respondents produced a break the CDC explicitly warns against crossing: trend lines should be broken between 2010 and 2011. Further staged changes in 2012 and 2014 to cell-phone eligibility screening. These are `OBSERVED`, dated, externally documented degradation events — exactly what BRIEF §22 asks for and refuses to let us invent |
| Fairness attributes | Sex, age group, race/ethnicity, education, income, marital status, tenure, state — all core, all annual |
| OOD opportunities | Year-to-year cohort composition changes; state-level holdout as a natural OOD population |
| Structural monitoring (A3) | **Real and abundant.** Optional modules rotate by year and by state; variable names change across years (the diabetes item is `DIABETE3` in some years, `DIABETE4` in others); columns appear and disappear between annual files. This is genuine schema drift, not injected |
| Operational simulation (A4) | Simulated as always; monthly submission cadence gives a natural batch structure to perturb |
| Access | Free public download from CDC, no registration, no DUA. ASCII and SAS Transport formats; ZIPs are ~44–84 MB per year |
| Compute | Trivial by modern standards: ~0.5–1 GB per decade after conversion to Parquet |

**Weakness:** it is survey data, not EHR. Self-reported, weighted (complex survey design — `_LLCPWT`, PSU, strata must be handled or explicitly ignored with justification), and each record is a person-year, not a clinical encounter.

### C2 — Diabetes 130-US Hospitals, 1999–2008 (UCI #296) ✅ recommended: EHR substrate

| Dimension | Assessment |
|-----------|-----------|
| Relevance | **Genuine EHR extract** — drawn from the Cerner Health Facts data warehouse, 130 US hospitals and integrated delivery networks. This is what preserves RQ3 |
| Size | 101,766 inpatient encounters, ~50 features |
| Modality | Mixed-type tabular EHR: demographics, administrative codes, utilisation counts, ICD-9 diagnoses, 23 medication columns, HbA1c and glucose results |
| Longitudinal structure | **Absent in the released file.** It covers ten years but carries no date, month or year column — only `encounter_id`, which is *sometimes assumed* to be time-ordered. That assumption is unverifiable and I will not build the temporal experiment on it |
| Target task | 30-day readmission (`readmitted` < 30 days) |
| Shift opportunities | Non-temporal but real: admission-source split (non-emergency vs emergency admissions) is used in the published shift literature as a genuine domain shift; also hospital-to-hospital and specialty-to-specialty |
| Fairness attributes | Race (6 levels incl. missing), gender, age in 10-year bands |
| OOD opportunities | Held-out admission types, rare specialties, unseen ICD-9 groups |
| Structural monitoring (A3) | Strong: real ICD-9 coding, and severe real missingness — `max_glu_serum` ~95% missing, `A1Cresult` ~83%, `medical_specialty` ~49%, `weight` almost entirely missing. Missingness *patterns* are the monitorable signal |
| Operational simulation (A4) | Simulated only |
| Access | Free, UCI ML Repository dataset 296, **CC BY 4.0**, single CSV, or via the `ucimlrepo` package |
| Compute | Negligible — a few MB |

**Weakness:** no timestamps, so it cannot carry the temporal replay that is the centrepiece experiment (BRIEF §21, §48, §63).

### C3 — MIMIC-IV / MIMIC-III Clinical Database **Demo** — smoke tests only
~100 patients, openly licensed without credentialing **[verify licence and credential status at download]**. Far too small for any experiment; useful only as BRIEF §40 Level-1 smoke-test fixtures with real EHR structure.

### Rejected

| Dataset | Why rejected |
|---------|--------------|
| MIMIC-IV, eICU-CRD, EHRSHOT | Credentialing — excluded by your constraint |
| Synthea, CMS DE-SynPUF | Synthetic. BRIEF §47 forbids synthetic data as evidence that HAVM works on healthcare data. Usable only for unit tests |
| SEER, HCUP NIS/NRD | Require a signed research agreement and/or payment — same class of friction you asked to avoid |
| NHANES | Open and real, but ~5k per 2-year cycle: too few windows, too little subgroup power |
| Kaggle "Diabetes Health Indicators" | A pre-processed derivative of BRFSS 2015. Use the CDC original — provenance matters more than convenience here |

## 3. Recommendation

**Two substrates, each with a defined role. Results are reported per substrate and never pooled.**

| Role | Dataset | Carries |
|------|---------|---------|
| **D1 — temporal replay (primary)** | **BRFSS**, monthly windows | Experiments 1, 2, 4, 5, 8, 11, 12; RQ1, RQ2, RQ4, RQ5, RQ5b, RQ6, RQ7 |
| **D2 — EHR modality (primary for RQ3)** | **Diabetes 130-US Hospitals** | Experiments 3, 6; RQ3, RQ8; controlled violations, OOD bake-off, missingness monitoring |
| **D3 — smoke tests** | MIMIC demo | Level-1 fixtures only |

This split is defensible on its merits, not just on availability: **D1 supplies real time and real documented shift events; D2 supplies real EHR provenance and real missingness.** BRIEF §29 asks whether the framework generalises when threshold values do not — two structurally different substrates is a better test of that than one dataset would be.

## 4. Prediction task per substrate (BRIEF §18)

**D1 — BRFSS: cardiovascular event history (`_MICHD`) from core-section features.**
Chosen because the core section is asked every year, so the feature set is stable enough to freeze a model on while still drifting; the label is a calculated variable maintained by CDC; prevalence is low enough for calibration and AUPRC to be informative; and subgroup attributes are present. Diabetes is the fallback if `_MICHD` proves unstable across years — but note the label variable itself is renamed across years, which is a real A3 event and must be handled by an explicit, versioned harmonisation map, never by silent renaming.

**D2 — Diabetes 130: 30-day readmission.**
Standard, well-benchmarked, and the shift split (non-ER → ER admissions) is established in the literature rather than invented by us.

**Models, both substrates:** prevalence baseline → regularised logistic regression → gradient boosting. Best validating model is frozen (BRIEF §49). No deep learning unless a neural arm is added explicitly for the energy-OOD comparison in RQ3.

## 5. What each monitor gets

| Monitor | D1 BRFSS | D2 Diabetes-130 |
|---------|----------|-----------------|
| A1 distributional | `OBSERVED` — real annual/monthly drift | `OBSERVED` — admission-source domains |
| A2 relational | `OBSERVED` with declared label delay | `OBSERVED` across domains |
| A3 structural | `OBSERVED` — module rotation, variable renames, columns appearing/vanishing | `OBSERVED` — extreme missingness patterns, ICD-9 vocabulary |
| A4 operational | `SIMULATED` | `SIMULATED` |
| Calibration | `OBSERVED` | `OBSERVED` |
| OOD | `OBSERVED` + `INJECTED` | `OBSERVED` + `INJECTED` — primary substrate for RQ3 |
| Fairness | `OBSERVED` — rich attributes, large groups | `OBSERVED` — coarser, smaller groups |
| Known event (Exp. 2) | **`OBSERVED` — the 2011 methodology break, externally documented** | none available |

The 2011 break is the single most valuable thing this dataset choice buys. It is a real, dated, third-party-documented change in the data-generating process, which means Experiment 2 does not have to fall back on injected perturbations, and the ground-truth onset is externally attested rather than declared by us.

## 6. Threats to validity introduced by this choice

Carried forward into the report:

1. **Survey ≠ EHR.** Any claim about deployment-time monitoring of clinical AI generalises from D1 only by analogy. Say so.
2. **Complex survey design.** BRFSS is weighted with PSU/strata. Either handle the design properly or state explicitly that the model is trained on unweighted records as a monitoring testbed and that prevalence estimates are therefore not population-representative. Both are defensible; silence is not.
3. **The 2011 break is a change in *measurement*, not in the patients.** It is a real distribution shift for the model, but it is an artefact of survey methodology rather than clinical change. That distinction must be stated wherever detection performance on this event is reported.
4. **Self-report error** is baked into every D1 feature and the label.
5. **D2 has no time axis.** No detection-delay result may be computed on D2, and `encounter_id` ordering must not be used as a proxy.
6. **Neither dataset supports a deployment claim.** This project sits at E3 at best, exactly as Stage 0 said.

## 7. Acquisition (reproducible, and runnable on your machine)

**D1 — BRFSS.** From `https://www.cdc.gov/brfss/annual_data/annual_data.htm`, take one annual file per year for the chosen span (SAS Transport `.XPT` inside a ZIP, or the fixed-width ASCII with the layout in that year's codebook). Recommended span: **2011–2021**, i.e. entirely post-break, with **2010 added separately** so the break itself can be replayed as the Experiment-2 event. Record the exact file URL, release date and SHA-256 of every download in the dataset registry — CDC re-releases corrected files, so a bare year label is not a version.

**D2 — Diabetes-130.** `pip install ucimlrepo`, then `fetch_ucirepo(id=296)`; or download the CSV directly from the UCI page. Record the same provenance triple. Cite as Clore, Cios, DeShazo & Strack (2014), UCI ML Repository, DOI 10.24432/C5230J.

**In this container:** neither host is reachable. Either run the fetch locally and upload the files, or I write the acquisition script and you run it. No data goes into Git (BRIEF §53) — the repo stores the fetch script, the URLs, the checksums and the schema, never the rows.

## 8. Compute estimate

| Stage | Estimate |
|-------|----------|
| BRFSS download, 11 years | ~0.5–1 GB compressed |
| XPT → Parquet conversion | minutes; ~1 GB on disk |
| Cohort + feature build | single machine, minutes |
| Model training (LR, GBM) | minutes on CPU |
| Full monthly replay, all monitors | dominated by MMD — use a linear-time estimator or subsampling with a measured error budget, per Stage 0 §8.2 |

No GPU. No distributed anything.

## 9. Open decisions before Gate 3

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | Substrate split | Two-substrate as above · D2 only (faster, no temporal experiment) · D1 only | **Two-substrate.** D2-only kills the centrepiece experiment |
| 2 | BRFSS span | 2011–2021 post-break · include 2010 to replay the break | **Include 2010**, held out as the Experiment-2 event |
| 3 | Survey weights | Handle design properly · train unweighted and state it | **Unweighted, stated** — the object of study is the monitoring system, not population prevalence |
| 4 | Which substrate to build first | D2 (single CSV, running today) · D1 (more download work) | **D2 first** for the pipeline and the frozen model, D1 in parallel as files arrive |
| 5 | Keep the credentialing door open? | Start CITI in the background · close it | Your call; nothing depends on it |

**Recommended next gate: G3** — data pipeline, temporal/domain split, dataset versioning, baseline models trained, evaluated and frozen, starting on D2 while D1 downloads. Per BRIEF §65 I will stop and report there rather than continuing into monitors.

---

### Sources

- CDC BRFSS annual data and documentation (record counts, file sizes, formats): `https://www.cdc.gov/brfss/annual_data/annual_2013.html`, `.../annual_2016.html`, `.../annual_2017.html`, `.../annual_2020.html`
- CDC BRFSS Comparability of Data, 2011 and later editions (2011 raking/cell-phone break; 2012 and 2014 eligibility changes): `https://www.cdc.gov/brfss/annual_data/2019/pdf/compare-2019-508.pdf`, `.../2022/pdf/Compare_2022-508.pdf`
- BRFSS codebooks (`IDATE`, `IMONTH`, `IDAY`, `IYEAR`): `https://www.cdc.gov/brfss/annual_data/2016/pdf/codebook16_llcp.pdf`
- UCI ML Repository dataset 296, Diabetes 130-US Hospitals 1999–2008 (size, licence, provenance): `https://archive.ics.uci.edu/dataset/296/diabetes+130-us+hospitals+for+years+1999-2008`
- Fairlearn dataset documentation (Health Facts provenance, readmission target): `https://fairlearn.org/main/user_guide/datasets/diabetes_hospital_data.html`
