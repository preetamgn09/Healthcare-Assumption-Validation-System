# Gate 8 — Stage Report (BRIEF §65)

## 1. What was implemented

Scalability measurement (RQ7), a proper repetition of the AHS stability finding, programmatic
figure generation, a one-command reproduction script, and a D1 ingestion tool that turns the
BRFSS schema from a hazard into an input.

**The stability result is the one that matters: it converts Gate 5's alarming-but-unrepeated
observation into an actionable engineering constraint.**

## 2. Files created

| Path | Purpose |
|------|---------|
| `scripts/run_g8.py` | EXP009 scalability, EXP010 stability |
| `scripts/make_figures.py` | Six figures, each generated from a results JSON |
| `scripts/prepare_d1.py` | BRFSS XPT → Parquet plus a real column inventory |
| `scripts/reproduce_all.sh` | Every experiment in order, from a clean checkout |
| `results/figures/*.png` | fig01–fig06 |

## 3. Tests executed

`python -m pytest tests/ -q` → **92 passed**, unchanged from Gate 7. This gate added
measurement and tooling, not new monitor logic.

## 4. Results — EXP010: AHS stability, 30 partitions per window size

Deployment domain partitioned without replacement, so this has none of the pool-exhaustion
confound that limited EXP004.

| Windows | Window size | mean AHS | sd | range | 5–95% span |
|---|---|---|---|---|---|
| 20 | ≈2,792 | 0.506 | 0.073 | 0.390 – 0.606 | **0.206** |
| 10 | ≈5,584 | 0.442 | 0.050 | 0.389 – 0.609 | 0.139 |
| 5 | ≈11,169 | 0.422 | 0.017 | 0.395 – 0.477 | **0.040** |

Governance band width (review − suspension) = 0.25.

**Finding 11 — AHS noise does shrink with window size, and the requirement is quantifiable.**
At ≈2,800 rows the 5–95% span on *unchanged data* is 0.206 — 82% of the entire governance
band. At ≈11,000 rows it falls to 0.040, or 16%. This resolves Gate 5's Finding 1 and the
EXP004 confound in one measurement, and it converts a complaint into a design rule:

> On this substrate, AHS windows need roughly 10,000 rows before the score's own noise is
> small relative to the bands it is compared against. Below that, band crossings are
> substantially sampling artefacts.

That number is substrate-specific, but the *method* for deriving it — partition unchanged
data, measure the AHS span, compare it to the band width — is general, cheap, and absent
from both papers. It is the most directly usable thing this project has produced.

**Finding 12 — AHS is not comparable across window sizes.** Mean AHS rises from 0.422 to
0.506 as windows shrink from ≈11,000 to ≈2,800 rows, on identical data. The score is biased
by window size, not merely noisier. So a daily AHS and a weekly AHS are different quantities
and must not be plotted on one axis or compared against one threshold — a trap the framework
as specified would walk straight into, since it defines the score without reference to
window size at all.

## 5. Results — EXP009: scalability (RQ7)

Hardware and package versions recorded in the results JSON. Full pipeline (load, cohort,
split, features): **1.8 s**.

| Window size | seconds | rows/second |
|---|---|---|
| 1,000 | 0.61 | 1,647 |
| 2,500 | 0.49 | 5,089 |
| 5,000 | 0.55 | 9,086 |
| 10,000 | 0.69 | 14,391 |
| 25,000 | 1.04 | 23,982 |
| 55,848 | 1.80 | 31,071 |

Peak RSS flat at 365 MB throughout.

**Monitoring cost is dominated by fixed overhead, not by data volume.** A 56× increase in
window size costs 3× the wall-clock. Reference size barely registers (0.42–0.84 s across a
10× range, and the ordering is not even monotone — that is measurement noise, not a trend),
because MMD subsamples and PSI is histogram-based. Adding the OOD and A4 monitors takes
n=5,000 from 0.55 s to 1.09 s, with a one-off detector fit of 0.7 s.

The practical consequence points the same way as Finding 11: **there is no computational
reason to use small windows.** Cost scales with the number of windows far more than with
their size, and small windows are precisely where AHS is unreliable. Both arguments favour
fewer, larger windows.

## 6. Figures

Six, each generated from a stored JSON with no hand-entered numbers:

| Figure | Question |
|---|---|
| fig01 AHS stability | RQ4 — is AHS stable enough for its own bands? |
| fig02 threshold sensitivity | RQ6 — sensitivity against alert burden |
| fig03 baseline ladder | RQ1 — does integration beat the alternatives? |
| fig04 OOD bake-off | RQ3 — do detector rankings transfer? |
| fig05 severity ramp | H3 — does AHS track severity? |
| fig06 scalability | RQ7 — how does cost scale? |

## 7. D1 preparation

`scripts/prepare_d1.py` reads BRFSS files you have downloaded, writes Parquet, and produces
a **column inventory**: every column, its dtype, its per-year missing rate, and which years
it appears in. It deliberately downloads nothing — hard-coding CDC URLs I cannot verify from
this environment would be the same class of unchecked assumption the project exists to catch.

The inventory is not administrative. BRFSS renames items across years and rotates modules in
and out, so the D1 config must be written from columns that are demonstrably present rather
than from remembered variable names. The year-to-year presence table doubles as ground truth
for A3 structural monitoring on that substrate.

## 8. Computational cost

EXP009+EXP010 ~4 minutes; figures ~5 seconds. Peak RSS 365 MB. No GPU at any point in the
project.

## 9. Known limitations

1. **RQ2 remains unstarted.** Blocked on BRFSS.
2. **Findings 11 and 12 are D2-specific.** The 10,000-row rule is a number for this
   substrate; the method generalises, the constant does not.
3. **Timings are single-machine, single-process**, on the hardware recorded in the JSON.
4. **Provenance still `MIRROR_UNVERIFIED`.**

## 10. Where the project stands

Eight gates, ten experiments, 92 tests, one command to reproduce everything. Every research
question except RQ2 has been addressed on D2:

| | Result |
|---|---|
| RQ1 integration | no measurable advantage; CI touches zero |
| RQ2 detection speed | **blocked — needs BRFSS** |
| RQ3 modality transfer | rankings do not transfer; uncertainty methods at chance |
| RQ4 AHS validity | unstable below ~10,000-row windows; biased by window size |
| RQ5 weight sensitivity | robust in the middle, catastrophic at the extremes |
| RQ5b normalisation | no detection effect; matters for severity resolution |
| RQ6 thresholds | clean trade-off curve; the specified 0.75 lands near the knee |
| RQ7 scalability | fixed-overhead dominated; favours fewer, larger windows |
| RQ8 subgroup detection | age disparity found beyond the null band with aggregates clean |
| RQ9 governance separation | 7 of 10 inappropriate suspensions prevented |

The through-line has not changed since Gate 6, and it has now survived three more
experiments: **the structural parts of HAVM earn their place; the composite score does not.**
The most useful contributions are the ones the framework does not contain — the permutation
null band for fairness, the AHS stability rule, the missing-monitor bracket, and the
measured failure of uncertainty-based OOD on tabular EHR.

## 11. Recommended next stage

**Gate 9 — BRFSS, or write up.** Two paths, and they are not exclusive:

1. **If BRFSS arrives:** temporal replay, RQ2, and a second substrate for RQ1. This is the
   only remaining source of genuinely new information.
2. **If it does not:** the D2 results already support a complete capstone with a coherent
   negative headline. The write-up would need no new experiments — only the evidence pack
   assembled from `results/`, which is what `research/` and the figures are already for.

The one task that should happen regardless is the UCI re-fetch, so that every number in the
write-up rests on verified provenance.
