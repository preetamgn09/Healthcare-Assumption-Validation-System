# Reproducibility

## One command

```bash
bash scripts/reproduce_all.sh
```

Installs dependencies, fetches and checksums the dataset, runs the tests, runs EXP001
through EXP010 in order, and regenerates every figure. Each stage reads only what the
previous one wrote. Nothing is hand-edited between stages, and no result is ever typed into
a document.

Set `D2_SOURCE=mirror` if the canonical archive host is unreachable from your network — but
see "Provenance" below before trusting anything produced that way.

## What every experiment records automatically

Written into each results JSON by `havm.utils.environment_record()`:

- UTC timestamp
- Git commit (or an explicit `NOT_A_GIT_REPO` marker)
- Python version, platform string, CPU count
- numpy, pandas, scikit-learn, scipy versions
- config file hash and monitor-config hash
- dataset SHA-256, row and column counts, cohort exclusion counts
- random seeds
- runtime, and for the scalability experiment, peak RSS

## Determinism

All seeds are declared in configuration, never in code. `test_split_is_deterministic`
asserts that two independent runs produce identical row ordering in every split. Model
selection, window construction, permutation bands, bootstrap resampling and Dirichlet draws
are all seeded.

The one deliberate exception: nothing reseeds between experiments, so running a single
script in isolation reproduces that script's results exactly, and running the full pipeline
reproduces all of them.

## Provenance

`configs/d2_diabetes.yaml` carries `expected_sha256` and `provenance_status`. The pipeline
**refuses to run on a checksum mismatch** rather than continuing with an unversioned file.

Current status is `MIRROR_UNVERIFIED`: the canonical archive host was unreachable from the
build environment, so the file came from a mirror and was verified against published
metadata — exact row and column counts, exact column names, and the published readmission
class distribution. Before any number is published, re-run:

```bash
python scripts/fetch_d2.py --source uci
```

and set `provenance_status: UCI_VERIFIED` once the checksum matches.

## Experiment identity

Results are never overwritten. A corrected run gets a new experiment ID; superseded runs
stay in `research/experiment_log.md` with the reason they were superseded. Two entries there
record numbers that were later replaced — the confounded severity ramp in EXP003 and the
row-count-gated fairness run in EXP002 — because in both cases the superseded result is the
reason the current design exists.

## What is not reproducible from this repository

- **D1 (BRFSS).** Not acquired. `scripts/prepare_d1.py` converts files you have downloaded
  and inventories their real columns, but downloads nothing: hard-coding source URLs that
  could not be verified from the build environment would be exactly the unchecked assumption
  this project exists to detect.
- **Patient-level data.** `data/` is git-ignored. The repository stores fetch scripts, URLs,
  checksums and schemas — never rows.
- **Hardware timings.** Scalability numbers are single-process on the machine recorded in
  the results JSON and will differ on yours. The shape of the curve should not.

## Test suite

```bash
python -m pytest tests/ -q      # 92 tests, ~5 seconds
```

Four categories: analytic guarantees with known answers (P = Q ⇒ MMD → 0, perfect
calibration ⇒ ECE → 0, AHS = 1 when nothing is violated, BH-FDR rejecting nothing under the
global null); leakage and determinism guards; monitor behaviour on constructed cases; and
audit-record completeness. Synthetic data appears only here, never as evidence.
