# Governance

The governance layer produces **policy decisions only**. Nothing in this system performs an
automated clinical action; the most severe state is a *recommendation* to suspend automated
prediction, recorded for a human. Everything here is a simulation of a policy (BRIEF §32)
and carries no evidence about how any institution would behave.

## States

`NORMAL → MONITOR → GOVERNANCE_REVIEW → HUMAN_REVIEW_REQUIRED → ABSTENTION_RECOMMENDED →
AUTOMATED_PREDICTION_SUSPENSION`

## The separation that matters

```
detection  →  harm assessment  →  governance decision  →  intervention
```

Harm levels: `NONE` (change detected, no measured effect), `POTENTIAL` (corroborated input
change, effect plausible but unmeasured), `MEASURED` (an outcome-facing metric moved past
its bound).

The taxonomy rests on **which** monitors moved, not how much. A1, A3, A4 and OOD observe the
*input*; calibration, fairness and A2 observe the model's *behaviour*. Only the second class
can establish harm. Two independently designed detectors must agree before an input change
is treated as corroborated, and a subgroup disparity inside its permutation null band is
discounted regardless of what the declared threshold says.

## Why the separation exists

Measured, not assumed. On the deployment domain, A1 reached a violation of 1.000 while
calibration stayed at ECE 0.0071 and discrimination fell 0.023 — large drift, intact
behaviour. Run identically on the same monitor output, the collapsed policy (AHS bands
straight to action) recommended suspension in 7 of 10 windows; the separated policy
recommended it in none.

## Escalation dynamics

Escalation requires persistence across consecutive windows. **De-escalation is immediate** —
holding a model under restriction after the condition has cleared is its own harm.

## Audit

Every window produces one append-only record containing the monitor raws and thresholds, the
AHS and its decomposition, the harm assessment, both governance decisions, the alert packet,
registry and config hashes, and rollback information. A test asserts self-containment: any
alert can be reconstructed from the log alone, without re-running anything.

The human decision field is populated only by a real reviewer. It is empty everywhere in
this project, and that is not an oversight — no human has reviewed any alert here.
