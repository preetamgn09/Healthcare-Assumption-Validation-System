# HAVM — Healthcare Assumption Validation Monitoring (capstone implementation)

An experimental testbed for the HAVM framework proposed in *Assumption Validation in
Deployed Healthcare AI/ML Systems* (ICCSI-2026). The framework is treated as a set of
**hypotheses to be tested**, not as an established design. Negative results are first-class
outputs.

The scientific question: does integrating multiple assumption monitors into a single
composite score detect meaningful degradation more reliably or earlier than independent
detectors — and if not, why not?

## Status

| Gate | Content | State |
|------|---------|-------|
| G0 | Paper analysis, research questions, scope, hypotheses | done — `research/` |
| G1 | Dataset selection under an open-access constraint | done — `research/dataset_selection.md` |
| G3 | Data pipeline, splits, versioning, baselines, model freeze | done — EXP001 |
| G4 | Monitors: A1, A3, calibration, fairness | done — EXP002 |
| G5 | AHS, triage, governance, audit, end-to-end replay | done — EXP003 |
| G6 | Thresholds, weights, normalisation, baseline ladder, ablation | done — EXP004–006 |
| G7 | A2, A4, OOD bake-off (RQ3), complete seven-monitor AHS | done — EXP007–008 |
| **G8** | **Scalability, AHS stability, figures, reproduction** | **done — EXP009–010** |
| G9 | Write-up: final report, reproducibility, docs | done |
| G10 | BRFSS temporal replay (RQ2) | **blocked — needs the BRFSS files** |

## Quick start

**New here? Read `HOW_TO_RUN.md`** — setup for Windows/macOS/Linux, plus a demo walkthrough.

```bash
pip install -r requirements.txt
python scripts/reproduce_all.py                  # everything, in order (~15 min)
python scripts/reproduce_all.py --quick          # tests + EXP001-003 + figures (~45 s)
```

Or step by step: `scripts/fetch_d2.py`, then `run_g3.py` … `run_g8.py`, then
`make_figures.py`. Tests: `python -m pytest tests/ -q` (92 tests).

Outputs land in `results/` — metrics, the frozen model and its card, and the assumption
registry. Everything is machine-generated; no number is ever typed by hand into a report.

## Headline result

Composite assumption scoring produced **no measurable detection advantage** over independent
detectors (ΔF1 +0.025, 95% CI [0.000, 0.085] — the width of one window). The structural
parts of the framework did hold up: separating detection from governance prevented 7 of 10
inappropriate suspension recommendations. Full evidence in `research/final_report.md`.

## Design rules this repo enforces

- **Nothing is hardcoded.** Thresholds, weights, cohort rules, features and splits all live
  in `configs/`. `src/` reads them.
- **The registry is the single source of truth.** Every monitor added later reads its
  configuration from `results/registry/`, never from its own module.
- **Provenance is tagged.** Registry entries carry `PAPER_SPECIFIED`, `BRIEF_SPECIFIED`,
  `OBSERVED` or `POLICY`. The AHS formula and every threshold are currently
  `BRIEF_SPECIFIED`/`POLICY` — no supplied paper defines them (see
  `research/paper_analysis.md` §0).
- **The deployment domain is sealed** until Gate 5. Its hash is recorded so the seal can be
  demonstrated rather than asserted.
- **Splits are by patient, never by encounter.** Enforced by test.
- **No patient data in Git.** `data/` is ignored; the repo stores fetch scripts, URLs,
  checksums and schemas.

## Layout

```
configs/     dataset, model, split, threshold and weight declarations
src/havm/    datasets/ features schema metrics models registry utils
scripts/     fetch_d2.py, run_g3.py
tests/       analytic metric tests, leakage and determinism guards
research/    paper analysis, RQs, scope, hypotheses, dataset selection,
             gate reports G3-G8, experiment log, final_report.md, reproducibility.md
docs/        architecture, monitoring, governance
results/     metrics/ models/ registry/  — machine-generated, never hand-edited
```

## Data

**D2 — Diabetes 130-US Hospitals (UCI #296)**, CC BY 4.0. Clore, Cios, DeShazo & Strack
(2014), DOI 10.24432/C5230J. Real EHR extract (Cerner Health Facts); no timestamps, so it
carries the modality and controlled-violation experiments, not temporal replay.

**D1 — BRFSS (CDC)**, public domain, pending. Carries the temporal replay: monthly windows
and the documented 2011 methodology break as a real degradation event.
