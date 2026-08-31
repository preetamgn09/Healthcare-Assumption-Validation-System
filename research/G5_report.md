# Gate 5 — Stage Report (BRIEF §65)

## 1. What was implemented

The AHS aggregator, the triage/harm-assessment stage, the governance state machine, the
audit trail, and a replay engine that serves both historical replay and simulated
streaming. EXP003 runs the full chain — data → frozen model → monitors → AHS → triage →
governance → audit — over twenty windows.

**This gate produced the project's first substantive negative results.** They are reported
here as findings, not patched away.

## 2. Files created

| Path | Purpose |
|------|---------|
| `src/havm/aggregation.py` | AHS with per-component decomposition, saturation, masking and missing-monitor analysis |
| `src/havm/triage.py` | Harm assessment; alert packet (BRIEF §14) |
| `src/havm/governance.py` | State machine (separated / collapsed variants) + append-only audit trail |
| `src/havm/replay.py` | Window construction: random partition, temporal, declared sequence |
| `scripts/run_g5.py` | EXP003 runner |
| `tests/test_aggregation.py` | 19 analytic tests |

**Modified:** `configs/monitors.yaml` gained the `ahs` and `governance` sections.

## 3. Tests executed

`python -m pytest tests/ -q` → **66 passed** (47 prior, 19 new), ~4 s.

New guarantees: AHS = 1 when nothing is violated and 0 when everything is; strictly
decreasing in any single component with others fixed; bounded in [0,1]; contributions sum
exactly to the deficit; a low-weight monitor at total violation cannot cross the review band
(H9, analytic then numeric); baseline-relative entry gives exactly zero at the baseline and
exactly 1.0 at baseline+threshold; input drift alone is not harm; two input detectors give
POTENTIAL not MEASURED; a disparity inside its null band is discounted; escalation requires
persistence while de-escalation is immediate; the separated variant never suspends on input
drift alone while the collapsed variant does; and every audit record is self-contained.

## 4. Results — EXP003

**Freeze-time baselines** (in-distribution validation): ECE 0.0060, ΔTPR 0.0745.

### Part A — `OBSERVED`: deployment domain, 10 windows, random partition

D2 has no time axis, so this is an arbitrary partition, not a trajectory. Its purpose is a
stability test: every window is drawn from the *same* distribution, so a well-behaved score
should be flat.

| | AHS |
|---|---|
| mean | 0.453 |
| standard deviation | 0.058 |
| range | 0.402 – 0.612 |

**Finding 1 — AHS is not stable on a homogeneous stream.** A spread of 0.21 across windows
that differ only by random assignment. For scale: the entire distance between the review
band (0.75) and the suspension band (0.50) is 0.25. **The noise in AHS is comparable to the
width of a governance band.** Under the separated variant the system spent six windows in
GOVERNANCE_REVIEW and three in ABSTENTION_RECOMMENDED with nothing changing underneath —
state churn driven by sampling, not by the model or the data.

This bears directly on RQ4/H1. A composite whose window-to-window noise approaches its
decision bands cannot support a claim of earlier or more reliable detection until the noise
is characterised and the bands are set relative to it. The fix is not a better weighting; it
is a reference band for AHS itself, of the kind already built for fairness.

**Finding 2 — missing monitors make the system look healthier.** A2, A4 and OOD are not yet
implemented. Under the declared weights their violations count as zero, giving AHS 0.685;
renormalised over the four monitors that actually ran, the same window scores 0.428. **A gap
of 0.26 — larger than a full governance band — produced purely by monitors being absent.**
The additive form cannot distinguish "this assumption holds" from "this assumption was not
measured", and the direction of the error is towards false reassurance. A monitoring system
that silently reports better health as its monitors fail is a hazard, and neither paper
addresses it. Both readings are computed on every window so the gap stays visible.

### Part B — `INJECTED`: declared severity ramp with recovery

Severities 0 → 1 → 0 over ten windows, window size held constant at n = 8,000.

| Severity | 0.00 | 0.00 | 0.25 | 0.50 | 0.75 | 1.00 |
|---|---|---|---|---|---|---|
| AHS | 0.432 | 0.629 | 0.316 | 0.175 | 0.175 | 0.241 |

**Finding 3 — H3 is falsified in this regime, for two distinct reasons.**

*Below severity 0.5, noise dominates.* The two severity-0 windows differ by 0.197 with
identical severity — the same instability as Part A.

*Above severity 0.5, saturation dominates.* At severity 0.50 all three contributing
monitors reach violation 1.000 and AHS floors at 0.175. Severity 0.50, 0.75 and 1.00 are
indistinguishable. The worked decomposition at the floor:

```
AHS = 0.175 (deficit 0.825)
  a1_distribution: violation 1.000 x weight 0.364 = 0.364  [SATURATED]
  calibration:     violation 1.000 x weight 0.273 = 0.273  [SATURATED]
  fairness:        violation 1.000 x weight 0.182 = 0.182  [SATURATED]
```

Every component pinned at its ceiling. The score cannot get worse, so detection delay and
severity are unmeasurable in this range. This was predicted analytically in
`implementation_hypotheses.md` H3; it is now measured.

**Finding 4 — separating detection from governance prevents inappropriate suspension
(H10 supported).** Identical monitor output, two policies:

| | separated | collapsed |
|---|---|---|
| Escalations (Part B) | 2 | 1 |
| Windows in AUTOMATED_PREDICTION_SUSPENSION | **0** | **7 of 10** |
| Windows in ABSTENTION_RECOMMENDED | 5 | 0 |

The collapsed variant, wired straight from the AHS bands to action, recommended suspending
automated prediction in seven of ten windows — including windows where the only trigger was
input drift with model behaviour inside its bounds. The separated variant never reached
suspension. In Part A the pattern repeats: collapsed reached suspension, separated did not.

**This is the clearest support any experiment has produced for a HAVM design principle** —
and note that it is support for *separation*, which is cheap and structural, not for
*aggregation*, which is where the framework's novelty is claimed.

### Audit

Twenty self-contained records at `results/audit/EXP003_audit.jsonl`. Each carries the
monitor raws and thresholds, the AHS and its decomposition, the harm assessment, both
governance decisions, the alert packet, the registry and config hashes, and rollback
information. Any alert can be reconstructed from the log without re-running anything.

## 5. Scientific assumptions

1. **Random partition is not a trajectory.** No detection-delay, alert-persistence or
   trajectory claim may be drawn from Part A. It tests stability only.
2. **The severity ramp's ordering is constructed**, not discovered. `INJECTED` throughout.
3. **The ramp's "clean" windows are already shifted** — they are drawn from the deployment
   domain, which genuinely differs from the training reference. Severity 0 means "no
   additional perturbation", not "no drift".
4. **The harm taxonomy rests on which monitors moved, not how much.** A1/A3/A4/OOD observe
   the input; calibration/fairness/A2 observe behaviour. Only the second class establishes
   harm. Defensible, but it is a design assertion of ours, not a result.
5. **Governance is a simulation** with no human in it (BRIEF §32). It says nothing about how
   a hospital would behave.

## 6. Engineering assumptions

1. Escalation requires persistence; de-escalation is immediate — holding a model under
   restriction after the condition clears is its own harm.
2. Weights renormalise over available monitors by default; both readings always computed.
3. Baseline-relative entry for calibration and fairness, absolute for A1 and A3.
4. AHS clipped to [0,1]; with Σw = 1 and v ∈ [0,1] the clip is never reached, and a test
   asserts it.

## 7. Known limitations

1. **AHS instability is now the binding problem.** Until it is characterised, no threshold
   or detection result is interpretable.
2. **No temporal replay.** Unchanged, and now the largest gap: every remaining RQ with a
   time component is blocked on BRFSS.
3. **Saturation** makes severity unmeasurable above ~0.5 in this configuration.
4. **A2, A4, OOD absent** — and Finding 2 quantifies what that absence costs.
5. **Provenance still `MIRROR_UNVERIFIED`.**
6. **One ramp, one seed.** Findings 1 and 3 need repetition across seeds before they carry
   real weight.

## 8. Computational cost

EXP003 ~4 minutes single-threaded, < 2 GB RAM. Dominated by the permutation null bands
(20 windows × 3 attributes × 200 permutations).

## 9. Recommended next stage

**Gate 6 — baselines, ablation, threshold/weight/normalisation sensitivity.** Three
additions to the plan, all forced by findings above:

1. **Characterise AHS noise first.** Repeated random partitions across seeds, giving a null
   band for AHS itself. Without it, Gate 6's threshold curves measure sampling noise.
2. **Add normalisation to the sensitivity grid as a first-class factor** (RQ5b). Finding 3
   makes the prediction concrete: saturation is a property of `threshold_relative`, so an
   unbounded or quantile normalisation should change the results more than any reweighting.
3. **Report the missing-monitor gap as a standing diagnostic**, not a one-off.

And in parallel, still: **download BRFSS.**
