# Architecture

A modular monolith. No microservices, no message broker, no distributed compute — none was
justified by a measured bottleneck, and reproducibility was ranked above architectural
ambition (BRIEF §58).

## The chain

```
dataset  →  frozen model  →  monitors  →  AHS  →  triage  →  governance  →  audit
                ↑               ↑           ↑        ↑            ↑
                └───────── assumption registry (single source of truth) ─────────┘
```

Every stage is independently testable, and the interfaces are the ones the brief specifies
(§55): `monitor(window, reference, registry) → MonitorResult`,
`compute_ahs(results, registry) → AHSResult`, `assess_harm(...) → HarmAssessment`,
`GovernanceEngine.step(...) → decision`, `AuditTrail.record(...)`.

## Modules

| Module | Responsibility |
|---|---|
| `datasets/d2.py` | verify → cohort → label → domain split → patient-grouped split |
| `features.py` | ICD-9 grouping, specialty vocabulary (fitted on training only) |
| `schema.py` | schema contract fit and violation detection |
| `models.py` | prediction baselines; the object being monitored |
| `metrics.py` | AUROC, AUPRC, Brier, ECE with bin detail, subgroup rates |
| `registry.py` | L2 assumption registry with provenance tagging |
| `monitors/` | base contract, distribution (A1), relational (A2), structural (A3), operational (A4), ood, calibration, fairness |
| `aggregation.py` | AHS with decomposition, saturation, masking, missing-monitor analysis |
| `triage.py` | harm assessment; alert packet |
| `governance.py` | state machine (separated / collapsed) + append-only audit |
| `replay.py` | window construction: random partition, temporal, declared sequence |
| `sweep.py` | rescore cached raw metrics under alternative policies |

## Three decisions worth knowing

**The registry is the only source of thresholds and weights.** Monitors read it; they never
read config files directly and never carry defaults. A monitor cannot run against a
configuration that was not recorded alongside its results.

**Raw metrics are computed once and rescored many times.** The expensive part of monitoring
is measurement; thresholds, weights, normalisation and ablation vary only the cheap part.
This is what made a grid of hundreds of configurations affordable, and it guarantees every
configuration is compared on identical measurements.

**One replay engine serves historical replay and simulated streaming.** They differ only in
how windows are cut, which is a config choice (BRIEF §31).

## Deliberately absent

No dashboard, no API, no database, no container. Each was assessed and none earns its cost:
the research questions are answered by scripts writing JSON, and a dashboard demonstrates
nothing scientific. `results/` is the interface.
