# Monitoring

Seven monitors, one contract. Each returns the same `MonitorResult` structure regardless of
what it measures, which is what lets aggregation, triage and audit be written once.

| Monitor | Assumption | Signal | Evidence class | Needs labels |
|---|---|---|---|---|
| `a1_distribution` | A1 | PSI per feature; KS/χ² with BH-FDR; linear-time MMD | OBSERVED | no |
| `a2_relational` | A2 | predicted-score PSI (label-free); AUROC delta (delayed) | OBSERVED | partly |
| `a3_structural` | A3 | schema conformance, missingness shift, vocabulary growth | OBSERVED | no |
| `a4_operational` | A4 | missing/delayed batches, latency, version changes | **SIMULATED** | no |
| `ood` | OOD | exposure rate beyond a reference quantile | OBSERVED | no |
| `calibration` | calibration | ECE against a freeze-time baseline | OBSERVED | yes |
| `fairness` | fairness | subgroup ΔTPR/ΔFPR with a permutation null band | OBSERVED | yes |

## Four things the implementation does that the framework does not specify

**Effect size drives violations; significance is evidence only.** At deployment sample sizes
22 of 25 features were significant under FDR while 5 exceeded the effect-size bound.
Significance measures n, not drift.

**Per-feature tests are FDR-corrected.** Without it, alert volume measures how many columns
the schema has.

**Subgroup disparities are compared against a permutation reference band**, not only against
a declared threshold, and groups are gated on a minimum *positive* count as well as a
minimum size — TPR is conditional on positives, so a row-count gate is the wrong instrument.

**Behaviour monitors enter the AHS as change from a freeze-time baseline.** The frozen model
already breached the fairness bound in-distribution, so an absolute-threshold monitor
contributes a constant violation from day one and the score starts below 1.0 for reasons
unrelated to drift.

## Measured properties of the AHS

Documented because each is a way the score misleads, and each is computed on every call:

- **Saturation** — `threshold_relative` maps everything past the bound to 1.0, so severity
  becomes unmeasurable; AHS floors and stops distinguishing moderate from extreme.
- **Masking** — a monitor with weight *w* moves AHS by at most *w*; if *w* < (1 − review
  band), a total violation of that assumption cannot by itself trigger review.
- **Missing monitors** — treating an absent monitor as zero overstates health; renormalising
  understates it. Both readings are always computed.
- **Window-size dependence** — AHS is both noisier and biased at small windows. Scores at
  different window sizes are different quantities and must not share a threshold.
