# HAVM — Paper Analysis (Stage 0)

**Status:** analysis only. No implementation code, no dataset downloads, no dependencies installed.
**Sources read in full:**

| ID | File | What it is |
|----|------|-----------|
| **P-NEW** | `HAVM_review_ICCSI2026_v3.docx` (and `HAVM_review_ICCSI2026_preview.pdf`, which is a render of the same content) | Structured narrative review, 25 papers / 8 domains, ICCSI-2026 (Springer LNCS/IFIP AICT format) |
| **P-OLD** | `Healthcare_Assumption_Validation_System__3_.pdf` | Earlier version of the same review, 20 papers / 7 domains, Springer Nature journal format |
| **BRIEF** | The project instruction document (§1–§71) | Implementation specification |

Per BRIEF §1, **P-NEW is treated as the primary research source.**

### Where the 20 required questions are answered

| Q | Question | Location |
|---|----------|----------|
| 1 | What exactly is HAVM? | §1 |
| 2 | What is directly supported? | §3 |
| 3 | What is merely proposed? | §4 |
| 4 | What is mathematically specified? | §5 |
| 5 | What is not specified? | §5 |
| 6 | Contradictions between versions | §2 |
| 7–8 | What to implement / exclude | `scope.md` §2–3 |
| 9–10 | Datasets / prediction task | `scope.md` §4–5 |
| 11–12 | Evaluable vs simulated monitors | `scope.md` §6 |
| 13 | Primary research contribution | §6 |
| 14 | Falsifying experiments | `implementation_hypotheses.md` |
| 15–16 | MVP vs ambitious | `scope.md` §7 |
| 17–19 | Compute / access / validity risks | `scope.md` §8 |
| 20 | Roadmap | `scope.md` §9 |

---

## 0. The finding that conditions everything else

**Neither uploaded paper contains the HAVM formalism that BRIEF §5–§13 instructs me to implement.**

Verified by full-text search of both documents. Absent from *both*:

- the **A1–A4 assumption taxonomy** (P-NEW and P-OLD both organise HAVM as **layers L1–L5**, not as assumption classes A1–A4);
- the **Assumption Health Score**: the string `AHS` does not occur in either document, nor does `1 − Σ w_k v_k(t)` or any composite scoring formula;
- **any numeric threshold**: `0.05` (ECE, ΔEO, ΔFPR), `0.20` (PSI), `0.75` / `0.50` (AHS governance bands) occur nowhere;
- **MMD** and **PSI** are never named as methods;
- **energy-based OOD scoring** appears only as one item in a list of detector families surveyed by Hong et al., never as a HAVM component;
- **ΔEO / ΔFPR** as defined metrics;
- the governance state machine `NORMAL → MONITOR → GOVERNANCE_REVIEW → HUMAN_REVIEW_REQUIRED → ABSTENTION_RECOMMENDED → AUTOMATED_PREDICTION_SUSPENSION`.

BRIEF §1 says the repository contains "an older implementation-oriented version" supplying "the mathematical definitions and concrete AHS formulation." **That document was not uploaded.** The older document that *was* uploaded (P-OLD) is a narrative review of the same kind as P-NEW, one draft generation earlier, with no mathematics in it at all.

**I have not fabricated a reconciliation.** Two options:

- **Option A — supply the missing document.** If an implementation-oriented HAVM specification exists, upload it; the AHS formulation, weights and thresholds then have a documented provenance and can be cited as *paper-specified*.
- **Option B — proceed, relabelling provenance.** Treat A1–A4, AHS, the weights, all thresholds and the governance states as **BRIEF-specified design decisions**, i.e. "Policy Assumptions" in the BRIEF §33 evidence taxonomy — *not* as claims inherited from a reviewed paper.

**Recommendation: Option B, with Option A folded in if the document surfaces.** Reason: the science does not depend on where the formula came from — AHS is a hypothesis to be tested either way (BRIEF §3). But the *write-up* does. Citing "the paper defines AHS as…" when no supplied paper defines it would be exactly the kind of unverifiable citation the review itself was cleaned up to remove (see §2, discrepancy D3). Every artefact I produce will therefore tag these as `[BRIEF-SPECIFIED]`, not `[PAPER-SPECIFIED]`.

This is a provenance problem, not a blocker. Nothing downstream changes except labels.

---

## 1. What exactly is HAVM? (Q1)

In both papers HAVM is **a proposed research direction, explicitly not a system**. P-NEW §6: "high-level design directions — not a system specification." Fig. 1 caption: "No element of this figure has been implemented or evaluated."

The proposal is a five-layer architecture with a `detect → judge → respond → record` loop:

| Layer | Function |
|-------|----------|
| **L1** Data ingestion | Multi-modal clinical acquisition with provenance timestamps |
| **L2** Assumption registry | Version-controlled, machine-readable assumption artefacts bound to model identity — "a model card made live" |
| **L3** Validation engine | Six co-located monitors reading thresholds from L2: distribution shift, OOD exposure, data fidelity, uncertainty/calibration, knowledge consistency, subgroup fairness |
| **L4** Response & adaptation | Violation-triggered actions with governance gates: alert, abstain, recalibrate, review, roll back |
| **L5** Governance & compliance | Auditable evidence chain, accountable organisational owner, returns revalidated assumptions to L2 |

Four design principles: (i) cross-domain co-location on a shared registry; (ii) **modality-specific validation of every monitor before it is trusted**; (iii) active rather than passive governance; (iv) explicit ownership and human-oversight boundaries.

The BRIEF's A1–A4 taxonomy is best read as a **re-cut of L3's monitor list along a different axis** (assumption class rather than method family). The mapping is clean and I propose keeping both:

| BRIEF | P-NEW L3 monitor | Grounded in |
|-------|------------------|-------------|
| A1 Distributional | Distribution shift | Bifet & Gavaldà [1], Rabanser et al. [18], Finlayson et al. [8], Krempl [15] |
| A2 Relational | (implicit — concept drift/calibration) | Guo et al. [11]; drift literature |
| A3 Structural | Data fidelity | Johnson [13], Wornow [23] — *infrastructural only, no monitoring method* |
| A4 Operational | — **no counterpart** | none |
| OOD | OOD exposure | Hong [12], Ulmer [21], Yang J. [24] |
| Calibration/UQ | Uncertainty/calibration | Feiner [6], Guo [11], Seoni [20], Viceconti [22] |
| Fairness | Subgroup fairness | Chen [3], Glocker [10], Yang Y. [25] |
| — | Knowledge consistency | Čyras [4], Romanov & Shivade [19] |

Two things fall out: **A4 (operational) has no evidence anchor in either corpus**, and A3 has substrate papers but no fidelity-monitoring method. Both must be built as design assertions, and labelled that way.

---

## 2. Contradictions between the two versions (Q6)

These are not editorial differences. Several change what the implementation is allowed to claim.

| # | Item | P-OLD | P-NEW | Which I use, and why |
|---|------|-------|-------|----------------------|
| **D1** | Corpus size / domains | 20 papers, 7 domains | 25 papers, 8 domains (adds "deployment monitoring lifecycle") | **P-NEW.** Also note P-OLD's Table 7 lists Chen et al. twice (#1 and #20) with the same reference key — its true corpus is ≤19, so "20" was never accurate. |
| **D2** | Date window | 2021–2024 imposed | No window; explicitly reversed because ADWIN (2007), Krempl (2014), Guo (2017), Rabanser (2019), MedNLI (2018), model cards (2019) all predate it | **P-NEW.** P-OLD cited some of these anyway, so its own criterion was self-violating. |
| **D3** | Screening funnel | Fig. 1 PRISMA-style: 1,130 → ~900 → ~220 → ~30 → 20 | Deliberately **removed**; states the counts would not be reproducible from a purposive search | **P-NEW.** Treat P-OLD's counts as unusable. Do not cite them anywhere in the capstone. |
| **D4** | Positioning table | Table 1 compares against four single-domain surveys (Silva, Hong Y., Seoni, Batool) | Removed; P-NEW §7.2 states those citations "could not be verified against published records and have been removed" | **P-NEW.** Several P-OLD references are unverifiable. Any P-OLD claim resting on refs [3] Awais, [13] Raza, [14] Hong, [20] Silva, [21] Hong Y., [23] Batool must be treated as unsupported. |
| **D5** | **Ensemble claim** | "multi-detector ensembles are *always* better than single-method ones" — stated as a design principle | Conditional: no single signal should be *assumed* adequate on an unvalidated modality; burden of demonstration falls on the deploying institution | **P-NEW.** This is the single most consequential difference for this project — see below. |
| **D6** | Tabular OOD evidence | Absent | Ulmer et al. [21]: most tested uncertainty techniques **failed** to identify clinically realistic OOD patient groups on tabular EHR | **P-NEW.** Directly governs the OOD design (BRIEF §7). |
| **D7** | L1 evidence anchor | Anchored to Raza et al. [13] MQTT/RBAC/HL7-FHIR pipeline, "98.9% accuracy" | Ref removed; L1 stated to have **no evidence anchor**, "a design assertion" | **P-NEW.** |
| **D8** | Evidence grading | None | E1–E4 scheme; result: **0 of 25 at E4** (live deployment), 12 E3, 4 E2, 9 E1 | **P-NEW.** This is the anchor for Gap 2 and for how the capstone must describe itself. |
| **D9** | Governance ownership | Unowned | Feng et al. [7] AI-QI hospital unit as accountable owner; Table 7 maps signal → trigger → owner → permitted action → evidence → audit record | **P-NEW.** Table 7 is the closest thing in either paper to the BRIEF's governance engine and should drive its design. |
| **D10** | Falsifiable RQs | None | §6.1 RQ1–RQ5 with comparators and stated disconfirming outcomes | **P-NEW.** Mapped in `research_questions.md`. |
| **D11** | "No single OOD detector dominates" | Asserted as Hong et al.'s finding | Not claimed; P-NEW describes Hong as a shift-type taxonomy | **P-NEW.** Do not repeat the P-OLD claim. |
| **D12** | MIMIC-IV citation | Sci Data **8** (2021), coverage 2008–2019 | Sci Data **10**, 1 (2023) | **P-NEW**, and verify the version actually downloaded — coverage differs by release and directly determines the temporal replay span. |
| **D13** | EHRSHOT description | Unquantified | 6,739 patients; CLMBR-T-base (141M params) pretrained on 2.57M records; 15 few-shot tasks; **not ICU-restricted** | **P-NEW.** The patient count is decisive for subgroup statistical power (see `scope.md` §4). |

### Why D5 matters more than the rest

The BRIEF's core hypothesis (§4) is that combining monitors beats isolated monitors. **P-OLD asserts that as an established convergence; P-NEW retracts it to a conditional prior.** If we inherit P-OLD's framing, the capstone is confirmatory and its result is nearly predetermined by construction. Under P-NEW's framing it is a genuinely open empirical question, on the exact modality (tabular EHR) where the one clinical data point in the corpus is a *negative* result [21].

The P-NEW framing is the scientifically defensible one and I will build to it. Practically: the implementation must be able to produce, and must preserve, the result "integration did not help."

---

## 3. What is *directly supported* by the corpus? (Q2)

Claims that rest on E3 clinical evidence and can be relied on:

1. **Model performance degrades across sites and cohorts** — Chekroud et al. [2].
2. **Fairness properties do not survive distribution change**; corrections optimal in-distribution fail out-of-distribution, and models encoding less demographic information often stay fairer — Yang, Y. et al. [25]. This is the strongest justification for fairness as a *runtime* monitor.
3. **Uncertainty estimates are not reliable OOD detectors on tabular EHR data** — Ulmer et al. [21]. Single institution, unreplicated, but it is the only direct evidence on our target modality.
4. **Deep networks are systematically overconfident; ECE diagnoses it; temperature scaling corrects it without retraining** — Guo et al. [11] (E2, vision benchmarks — transfer to tabular GBMs is an inference, not a finding).
5. **Two-sample testing on pre-trained representations is the strongest shift detector tested; detecting a shift and judging it harmful are separate steps** — Rabanser et al. [18] (E2, non-clinical; P-NEW explicitly calls the ranking "a starting hypothesis for clinical instantiation").
6. **Pipeline-level uncertainty diverges from per-stage estimates** — Feiner et al. [6] (imaging pipelines; only weakly relevant to a single-stage tabular model).
7. **MIMIC-IV and EHRSHOT exist and are longitudinal** — Johnson [13], Wornow [23]. Both papers are careful that these are *substrates*, not monitoring contributions.
8. **Static documentation lapses silently** — model cards [17], datasheets [9] are authored once with no mechanism to detect that their claims have expired. This is the strongest motivation for the versioned Assumption Registry, and it is an argument, not an experiment.

## 4. What is *merely proposed*? (Q3)

Everything architectural. Specifically:

- All five layers L1–L5 and the detect–judge–respond–record loop (P-NEW Fig. 1: "No element of this figure has been implemented or evaluated").
- Every row of Table 7 (signal → trigger → owner → action → evidence → audit). P-NEW: "no row has been evaluated in deployment"; "the thresholds in particular are placeholders."
- The claim that co-location improves alert precision (stated as RQ1, i.e. as an open question).
- The AI-QI unit as the accountable owner — a proposal in Feng et al. [7], with no operating record.
- L1 in its entirety.
- **Plus everything in §0**: A1–A4, AHS, weights, thresholds, governance states.

**Zero papers at E4.** No claim in this project may be phrased as though monitoring has been shown to work in deployment.

## 5. Mathematically specified vs unspecified (Q4, Q5)

**Specified anywhere in the supplied material:**

- ADWIN — variable-size windowing with Hoeffding-bound tests, parameter-free, formal FP/FN guarantees (via [1], named but not reproduced in either review).
- ECE and temperature scaling (via [11], named, not reproduced).
- Two-sample testing on pre-trained representations (via [18], named, not reproduced).
- `AHS(t) = 1 − Σ wₖ vₖ(t)`, `Σ wₖ = 1`, `AHS ∈ [0,1]` — **from BRIEF §10 only.**

**Not specified anywhere — these are the real design work:**

1. **The normalisation functions vₖ.** MMD, PSI, ECE, ΔTPR and schema-diff counts live on incommensurable scales; mapping each to [0,1] requires a squashing function, and *that choice is a free parameter nobody has constrained*. I expect it to dominate the weights in influence. BRIEF §11 treats weights as the research variable and is silent on normalisation; I propose adding a normalisation-sensitivity experiment (see `research_questions.md` RQ5b).
2. **Weights wₖ** — no defensible default exists in either paper.
3. **All thresholds** — P-NEW calls its own placeholders unvalidated.
4. **Window size and monitoring cadence.**
5. **Multiple-comparisons control.** Per-feature drift tests × features × windows generates false positives mechanically. Neither paper addresses it. Requires FDR control; otherwise "alert volume" results are artefacts.
6. **Ground truth for a "true alert."** No paper defines what counts as a detection worth having. Without a pre-registered definition, precision and recall are unmeasurable. This is the project's central measurement problem and must be settled before any experiment runs (see `scope.md` §8.3).

**One mathematical correction to the BRIEF.** §11 asks whether "two severe violations cancel out because of normalization." Under `AHS = 1 − Σ wₖvₖ` with `vₖ ≥ 0`, **cancellation is impossible** — every term is subtractive, so violations can only compound. The real failure modes of this functional form are different, and the experiments should target these instead:

- **Masking/dilution** — a maximal violation on a low-weight monitor (w = 0.05 → at most 0.05 of AHS) is invisible against the governance bands.
- **Saturation** — Σwₖvₖ → 1 floors AHS at 0; beyond that, severity is unobservable and detection delay becomes uninterpretable.
- **Correlated double-counting** — A1 drift and OOD exposure are not independent; the same underlying change is counted twice, mechanically inflating apparent sensitivity.
- **Compensation across time**, not across monitors: recovery in one signal can offset onset in another within a window, flattening the trajectory.

## 6. Proposed primary research contribution (Q13)

Not "we built HAVM." The defensible contribution is:

> **An open, reproducible testbed and the first empirical comparison of composite-score aggregation (AHS) against independent per-monitor alerting on longitudinal tabular EHR data, under a pre-registered definition of clinically meaningful degradation — reporting negative results.**

Three sub-contributions, in descending confidence of delivering:

1. **Aggregation analysis** (masking, saturation, correlation double-counting, normalisation sensitivity) — mathematically motivated, cheap to run, novel because no one has published an AHS-style score to critique. Deliverable even if the dataset access story goes badly.
2. **Modality-transfer replication** — P-NEW RQ3, extending Ulmer et al. [21] from uncertainty methods to shift detectors on tabular EHR. A replicated negative result is a real publishable finding.
3. **Integration-value test** — BRIEF §20 baseline ladder. Highest scientific value, highest dependence on data access and on the ground-truth definition holding up.

Note what this deliberately excludes: any claim about clinical utility, patient safety, regulatory compliance, or deployment readiness. The corpus contains nothing at E4 and this project will not reach E4 either — it will sit at **E3 at best**, and should describe itself that way.

---

## 7. Open items requiring your decision

| # | Item | Options | My recommendation |
|---|------|---------|-------------------|
| 1 | Missing implementation-oriented paper (§0) | A: upload it · B: relabel as BRIEF-specified | **B**, switch to A if it exists |
| 2 | Which paper's ensemble framing (D5) | P-OLD categorical · P-NEW conditional | **P-NEW** |
| 3 | Is this capstone connected to the ICCSI-2026 submission? | Independent · feeds a follow-up paper | Affects whether findings must be held for publication — please confirm |
| 4 | A1–A4 vs L1–L5 vocabulary | Pick one · maintain both with a mapping | **Both**, with the §1 mapping table in the registry, so results stay legible to readers of the paper |
