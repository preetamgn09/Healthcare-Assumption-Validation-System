"""Triage — the harm assessment stage between detection and governance.

EXP002 established why this stage has to exist rather than being an architectural nicety:
the deployment domain produced max PSI 3.33 (violation 1.000) while aggregate calibration
stayed at ECE 0.0071, well inside its bound. A governance layer wired straight to detection
would escalate a model whose outputs were still behaving. Rabanser et al. separate
detecting a shift from judging whether it is harmful; this module is that separation.

Harm levels:
  NONE       change detected, no measured effect on model behaviour
  POTENTIAL  change detected and corroborated, effect plausible but not measured
  MEASURED   an outcome-facing metric has moved beyond its bound

The distinction rests on which monitors moved, not on how much. A1 and A3 observe the
INPUT; calibration and fairness observe the model's BEHAVIOUR. Only the second class can
establish harm.
"""
from __future__ import annotations

BEHAVIOUR_MONITORS = {"calibration", "fairness", "a2_relational"}
INPUT_MONITORS = {"a1_distribution", "a3_structural", "a4_operational", "ood"}


def assess_harm(results: list[dict], ahs_result: dict, registry: dict) -> dict:
    gov = registry["monitor_config"]["governance"]
    by_name = {r["monitor"]: r for r in results}

    triggered = {r["monitor"] for r in results if r["triggered"]}
    input_triggered = sorted(triggered & INPUT_MONITORS)
    behaviour_triggered = sorted(triggered & BEHAVIOUR_MONITORS)

    # Corroboration: a single detector is not enough to declare harm (P-NEW Table 7).
    corroborated = len(input_triggered) >= 2 or bool(behaviour_triggered)

    # A disparity inside its permutation null band is not evidence of anything, whatever
    # the declared threshold says (EXP002 finding c).
    noise_only = []
    fair = by_name.get("fairness")
    if fair and fair["triggered"]:
        exceeds = fair["raw"].get("exceeds_null_band")
        if exceeds is False:
            noise_only.append("fairness")
            behaviour_triggered = [m for m in behaviour_triggered if m != "fairness"]

    if behaviour_triggered:
        level = "MEASURED"
        rationale = (f"Model behaviour moved: {', '.join(behaviour_triggered)} beyond bound.")
    elif input_triggered and corroborated:
        level = "POTENTIAL"
        rationale = (f"Input change corroborated by {len(input_triggered)} independently "
                     f"designed detectors ({', '.join(input_triggered)}), with no measured "
                     "change in model behaviour.")
    elif input_triggered:
        level = "POTENTIAL" if not gov["require_corroboration"] else "NONE"
        rationale = (f"Input change flagged by {', '.join(input_triggered)} only. "
                     "Uncorroborated: a single detector is not sufficient to declare harm.")
    else:
        level = "NONE"
        rationale = "No monitor exceeded its declared bound."

    if noise_only:
        rationale += (f" Discounted as within sampling noise: {', '.join(noise_only)} "
                      "(disparity inside its permutation null band).")

    affected = None
    if fair and fair["raw"].get("worst_pair"):
        attr, high, low = fair["raw"]["worst_pair"]
        affected = f"{attr}: {low} vs {high}"

    return {
        "harm_level": level,
        "rationale": rationale,
        "input_monitors_triggered": input_triggered,
        "behaviour_monitors_triggered": behaviour_triggered,
        "corroborated": corroborated,
        "discounted_as_noise": noise_only,
        "affected_population": affected,
        "ahs": ahs_result["ahs"],
    }


def alert_packet(window_id, results: list[dict], ahs_result: dict, harm: dict,
                 governance: dict, registry: dict) -> dict:
    """The human-facing triage record (BRIEF §14). Every field is drawn from measurement;
    nothing here is a clinical recommendation."""
    worst = max(ahs_result["components"].items(),
                key=lambda kv: kv[1]["contribution_renormalised"], default=(None, {}))
    name, comp = worst
    src = next((r for r in results if r["monitor"] == name), {})

    return {
        "window_id": window_id,
        "what_happened": harm["rationale"],
        "assumption_violated": src.get("assumption"),
        "metric_that_triggered": name,
        "current_value": comp.get("raw"),
        "threshold": src.get("threshold"),
        "baseline": comp.get("derivation", {}).get("baseline"),
        "severity_harm_level": harm["harm_level"],
        "ahs": ahs_result["ahs"],
        "ahs_impact": comp.get("contribution_renormalised"),
        "affected_population": harm["affected_population"],
        "governance_state": governance["state"],
        "recommended_investigation": _investigation(harm, name),
        "evidence_class": src.get("evidence_class"),
        "caveats": ahs_result["notes"] + src.get("notes", []),
    }


def _investigation(harm: dict, worst_monitor: str | None) -> str:
    if harm["harm_level"] == "NONE":
        return "No investigation warranted. Continue routine monitoring."
    if harm["harm_level"] == "POTENTIAL":
        return (f"Investigate the source of input change ({worst_monitor}). Establish "
                "whether the shift is a case-mix change, an upstream data change, or a "
                "coding change before considering any action.")
    return ("Investigate model behaviour change: check subgroup composition against "
            "case mix, and confirm the effect persists on the next window before acting. "
            "No automated clinical action is recommended by this system.")
