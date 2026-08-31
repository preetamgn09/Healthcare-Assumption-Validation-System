# Gate 7 (D2 portion) — Stage Report (BRIEF §65)

## 0. What is blocked, and why this gate looks different

Gate 7 was scoped as the BRFSS temporal replay. **BRFSS has not been downloaded, and this
environment cannot reach cdc.gov** — the network is restricted to package repositories.
That work cannot start until the annual files exist locally or are uploaded, and no amount
of effort here substitutes for them. RQ2 (detection speed) remains entirely unstarted.

Rather than stall, this gate took the most valuable work that is *not* blocked by the
missing time axis: completing the monitor set (A2, A4, OOD) and running **RQ3**, which is
the second-most valuable question in the project and for which D2 — a real EHR extract — is
the right substrate rather than a compromise.

## 1. What was implemented

A2 relational, A4 operational, and a six-detector OOD module, all reading the registry.
EXP007 answers RQ3; EXP008 closes the missing-monitor gap opened by EXP003 Finding 2.

## 2. Files created

| Path | Purpose |
|------|---------|
| `src/havm/monitors/relational.py` | A2 (label-free + label-dependent signals, declared label delay) and A4 (simulated operational events) |
| `src/havm/monitors/ood.py` | Six tabular OOD detectors + window-level exposure monitor |
| `scripts/run_g7.py` | EXP007, EXP008 |
| `tests/test_monitors_extended.py` | 14 tests |

**Modified:** `configs/monitors.yaml` gained `a2_relational`, `a4_operational`, `ood`.

## 3. Tests executed

`python -m pytest tests/ -q` → **92 passed** (78 prior, 14 new), ~5 s.

## 4. Results — EXP007: the OOD bake-off (RQ3)

Detectors fitted on the training reference; each OOD group separated from the rest of the
deployment domain. Groups were defined by clinical criteria **fixed before any detector was
scored**. AUROC:

| Group (n) | mahalanobis | knn | isolation forest | pred. entropy | max softmax | energy |
|---|---|---|---|---|---|---|
| Paediatric & adolescent | **0.930** | 0.431 | 0.609 | 0.235 | 0.235 | 0.802 |
| Rare specialty | 0.548 | 0.545 | 0.522 | 0.538 | 0.538 | 0.396 |
| Extreme prior utilisation | 0.786 | **0.946** | 0.656 | **0.979** | **0.979** | 0.016 |
| **Mean** | **0.755** | 0.641 | 0.596 | 0.584 | 0.584 | 0.405 |

Family means: **uncertainty-based 0.524, distance/density-based 0.664.**
Within 0.10 of chance on average: isolation forest, predictive entropy, max softmax, energy.

**Finding 7 — Ulmer et al. replicates in a new direction.** The uncertainty family averages
0.524, which is chance. Two of the three (predictive entropy and max softmax) are monotone
equivalents in a binary model, so their identical scores are a correctness check rather than
two agreeing pieces of evidence — a test now asserts that relationship. On this real EHR
extract, model uncertainty is not usable as an OOD detector, exactly as the one clinical
data point in the reviewed corpus predicted.

**Finding 8 — the model is most confident where patients are least represented.** On the
paediatric and adolescent group, predictive entropy scores AUROC **0.235** — far *below*
chance. Inverted, not merely uninformative: the model is systematically **more** confident
on the patients whose age band is nearly absent from training. That is the silent-failure
mode the review's introduction describes, measured directly, and it is the strongest
argument in the whole project for why an independent input-side detector is needed rather
than trusting the model to signal its own ignorance.

**Finding 9 — the brief's specified OOD method performs worse than chance.** The energy
score averages 0.405 and reaches **0.016** on extreme prior utilisation — almost perfectly
anti-correlated with being out of distribution. Two caveats, both material. Energy is
defined over classifier logits; the frozen gradient-boosted model has no logit vector, so
this is computed on a logistic regression fitted to the same features, and the substitution
is reported wherever the number appears. And a strongly inverted detector is informative
when negated — the failure is one of sign convention as much as of discrimination. What it
is not is a method that can be adopted from the imaging literature and trusted on tabular
EHR data, which is precisely the modality-transfer claim RQ3 exists to test.

**No detector handles the hardest group.** Rare specialty sits at 0.52–0.55 for everything —
a genuinely novel category that nothing in this bake-off detects.

**Group excluded:** `unseen_admission_type` had only 18 members in the deployment domain,
below the minimum of 50, and was dropped rather than reported at that size.

## 5. Results — EXP008: the complete seven-monitor AHS

| Monitor | violation | evidence class | triggered |
|---|---|---|---|
| a1_distribution | 1.000 | OBSERVED | yes |
| a2_relational | 0.780 | OBSERVED | no |
| a3_structural | 0.200 | OBSERVED | yes |
| a4_operational | 0.000 | SIMULATED | no |
| ood | 0.267 | OBSERVED | no |
| calibration | 0.141 | OBSERVED | no |
| fairness | 1.000 | OBSERVED | yes |

**Finding 10 — a correction to EXP003 Finding 2.** With all seven monitors measured, the
true AHS on the deployment domain is **0.481**. The two Gate-5 approximations bracket it:

| | AHS |
|---|---|
| four monitors, missing treated as zero | 0.677 |
| four monitors, weights renormalised | 0.412 |
| **seven monitors, measured** | **0.481** |

EXP003 concluded that absent monitors bias the score toward false reassurance. That is
right for the missing-as-zero policy — 0.677 against a true 0.481, overstating health by a
full governance band. But renormalisation is biased too, in the *opposite* direction
(0.412), because it assumes the absent monitors would have looked like the present ones on
average, and here they looked considerably better. **Neither policy is safe; the direction
of the error is data-dependent, and only measuring the monitor tells you which way it
went.** The Gate 5 report has been left as written and this correction recorded against it,
per the no-overwriting rule.

**A2 has a real signal and it is label-free.** Score-distribution PSI drove the violation
(0.780); discrimination loss was only 0.023 (AUROC 0.649 against a frozen 0.672), well
inside the 0.05 bound. So the label-blind and label-available variants gave the *same*
violation here — which is convenient rather than by design, and would not hold if
discrimination had degraded. Note the pattern once more: massive covariate drift, essentially
intact discrimination and calibration.

**A4 reported zero** because the simulated batch was healthy. It is exercised properly by
tests, not by this run, and is labelled `SIMULATED` everywhere it appears.

## 6. Scientific assumptions

1. **OOD groups are proxies.** They are clinically motivated subpopulations, not verified
   out-of-distribution cases. Ulmer's design used clinically realistic groups for the same
   reason — no public dataset labels OOD status.
2. **The energy substitution** is documented above and is a deviation from the brief,
   made because the alternative was a category error.
3. **Detectors were fitted once on the full training set**, not per window. Per-window
   refitting would leak deployment information.
4. **A4 is invented telemetry.** No claim of any kind attaches to it.

## 7. Known limitations

1. **RQ2 is unstarted and blocked on BRFSS.**
2. **One deployment domain, one model, one dataset** for RQ3. Ulmer's result was also single
   institution; this replication inherits that limitation rather than resolving it.
3. **Three OOD groups**, one dropped for size.
4. **Provenance still `MIRROR_UNVERIFIED`.**

## 8. Computational cost

~5 minutes. Fitting six detectors on 27,530 reference rows and scoring 55,848 deployment
rows dominates; the Ledoit-Wolf covariance on the one-hot block is the single largest cost.

## 9. Where this leaves the hypotheses

| | |
|---|---|
| H1 integration improves precision | not supported (G6) |
| H3 AHS monotone in severity | falsified (G5) |
| H4 robust to weights | partly — fails at the extremes (G6) |
| H5 normalisation dominates weights | not supported, restated (G6) |
| **H8 detector rankings do not transfer to tabular EHR** | **supported (G7)** |
| H9 low-weight masking | confirmed (G5) |
| H10 separation reduces escalation | supported (G5) |

Three of the framework's structural claims hold; its two novel quantitative claims —
composite scoring and transferable detection — do not. H8's support is the clearest positive
result the project has produced, and it is a result *about the field's methods*, not about
HAVM's own machinery.

## 10. Recommended next stage

**Still Gate 7 proper: BRFSS.** Two things are needed from you and only from you:

1. Download the BRFSS annual files (2010–2021) and put them where the project can read them.
2. Re-fetch D2 from UCI so provenance stops being `MIRROR_UNVERIFIED`.

Until the first arrives, the remaining unblocked work on D2 is small and of diminishing
value: a scalability run (RQ7), and repeating EXP003's stability finding across more seeds.
Both are worth doing; neither changes any conclusion.
