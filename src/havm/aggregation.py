"""Assumption Health Score.

    AHS(t) = 1 - Σ wₖ · vₖ(t)

Provenance: this formula is BRIEF_SPECIFIED. No supplied HAVM paper defines it
(research/paper_analysis.md §0). It is implemented in order to be tested, not because it
is established.

Three properties of the additive form are computed on every call rather than left as
theory, because each is a way the score can mislead:

  saturation   vₖ = 1.0 means severity beyond the threshold is invisible. Two windows with
               wildly different disparities produce identical scores (H3).
  masking      a monitor with weight w can move AHS by at most w. If w < (1 - review band),
               a TOTAL violation of that assumption cannot by itself trigger review (H9).
  missing      an absent monitor contributes 0 under the naive reading, which makes a
               system with broken monitors look HEALTHIER than one with working ones.
               Both readings are returned so the gap is visible.
"""
from __future__ import annotations

from havm.monitors.base import normalise


def _entry_violation(result: dict, mode: str, baselines: dict, registry: dict) -> tuple[float, dict]:
    """Return the violation value entering the AHS, plus an explanation of how it was derived."""
    name = result["monitor"]
    if mode == "absolute" or name not in baselines:
        return result["violation"], {"mode": "absolute", "raw_violation": result["violation"]}

    norm = registry["monitor_config"]["normalisation"]["method"]
    base = baselines[name]
    metric_key, threshold_key = base["metric_key"], base["threshold_key"]
    current = result["raw"].get(metric_key)
    threshold = result["threshold"].get(threshold_key)
    if current is None or threshold in (None, 0):
        return result["violation"], {"mode": "absolute_fallback", "reason": "metric or threshold unavailable"}

    delta = max(float(current) - float(base["value"]), 0.0)
    v = normalise(delta, threshold, norm)
    return v, {
        "mode": "baseline_relative", "metric": metric_key, "current": float(current),
        "baseline": float(base["value"]), "delta": delta, "threshold": float(threshold),
        "absolute_violation_for_reference": result["violation"],
    }


def compute_ahs(results: list[dict], registry: dict) -> dict:
    cfg = registry["monitor_config"]["ahs"]
    weights_all = cfg["weights"]
    baselines = registry.get("freeze_baselines", {})

    present = {r["monitor"]: r for r in results}
    missing = [m for m in weights_all if m not in present]

    # Two weightings: as declared (missing -> 0) and renormalised over what actually ran.
    available_weight = sum(weights_all[m] for m in present if m in weights_all)
    components, deficit_declared, deficit_renorm = {}, 0.0, 0.0

    for name, result in present.items():
        if name not in weights_all:
            continue
        w_declared = weights_all[name]
        w_renorm = w_declared / available_weight if available_weight else 0.0
        mode = cfg["entry_mode"].get(name, "absolute")
        v, explanation = _entry_violation(result, mode, baselines, registry)

        deficit_declared += w_declared * v
        deficit_renorm += w_renorm * v
        components[name] = {
            "violation_entering_ahs": v,
            "weight_declared": w_declared,
            "weight_renormalised": w_renorm,
            "contribution_declared": w_declared * v,
            "contribution_renormalised": w_renorm * v,
            "saturated": v >= 1.0,
            "max_possible_contribution": w_declared,
            "derivation": explanation,
            "raw": result["raw"],
            "triggered_own_threshold": result["triggered"],
        }

    ahs_declared = max(0.0, min(1.0, 1.0 - deficit_declared))
    ahs_renorm = max(0.0, min(1.0, 1.0 - deficit_renorm))
    policy = cfg["missing_monitor_policy"]
    ahs = ahs_renorm if policy == "renormalise" else ahs_declared

    review_band = registry["monitor_config"]["governance"]["bands"]["review"]
    masked = [
        name for name, w in weights_all.items()
        if w < (1.0 - review_band)
    ]

    notes = []
    if missing:
        notes.append(
            f"{len(missing)} of {len(weights_all)} monitors absent ({', '.join(missing)}). "
            f"Under the declared weights their violations count as zero, giving AHS "
            f"{ahs_declared:.3f}; renormalised over the monitors that actually ran, "
            f"AHS is {ahs_renorm:.3f}. A missing monitor makes the system look healthier — "
            "the additive form cannot distinguish 'assumption holds' from 'not measured'."
        )
    saturated = [n for n, c in components.items() if c["saturated"]]
    if saturated:
        notes.append(
            f"Saturated: {', '.join(saturated)}. Severity beyond the threshold is not "
            "represented; these components cannot get worse."
        )
    if masked:
        notes.append(
            f"Masked at the review band of {review_band}: {', '.join(masked)}. A total "
            "violation of any of these cannot by itself trigger review, because its weight "
            f"is below the {1 - review_band:.2f} deficit required."
        )

    return {
        "ahs": ahs,
        "ahs_declared_weights": ahs_declared,
        "ahs_renormalised": ahs_renorm,
        "missing_monitor_policy": policy,
        "deficit": 1.0 - ahs,
        "components": components,
        "missing_monitors": missing,
        "saturated_components": saturated,
        "masked_components": masked,
        "notes": notes,
    }


def explain(ahs_result: dict, top_n: int = 3) -> str:
    """Answer 'why did AHS fall to X?' in plain text, ordered by contribution."""
    ranked = sorted(ahs_result["components"].items(),
                    key=lambda kv: kv[1]["contribution_renormalised"], reverse=True)
    lines = [f"AHS = {ahs_result['ahs']:.3f} (deficit {ahs_result['deficit']:.3f})"]
    for name, c in ranked[:top_n]:
        if c["contribution_renormalised"] <= 0:
            continue
        lines.append(
            f"  {name}: violation {c['violation_entering_ahs']:.3f} x weight "
            f"{c['weight_renormalised']:.3f} = {c['contribution_renormalised']:.3f}"
            + ("  [SATURATED]" if c["saturated"] else "")
        )
    if not ranked or all(c["contribution_renormalised"] <= 0 for _, c in ranked):
        lines.append("  no monitor contributed a deficit")
    return "\n".join(lines)
