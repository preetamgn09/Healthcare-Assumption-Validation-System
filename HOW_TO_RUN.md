# How to run this, and how to present it

## Part 1 — Running it

### One-time setup

You need Python 3.11 or newer. Check with `python --version` (Windows) or
`python3 --version` (macOS/Linux).

```bash
cd HAVM
python -m venv .venv
```

Activate it:

| System | Command |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows CMD | `.venv\Scripts\activate.bat` |
| macOS / Linux | `source .venv/bin/activate` |

Then:

```bash
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run
`Set-ExecutionPolicy -Scope Process RemoteSigned` first.

### Run everything

```bash
python scripts/reproduce_all.py
```

Downloads the dataset, verifies its checksum, runs the 92 tests, runs all ten experiments in
order, and regenerates every figure. About **15 minutes** end to end on a laptop. It stops at
the first failure and tells you which step broke rather than continuing on a bad
intermediate result.

Useful flags:

| Flag | Effect |
|---|---|
| `--quick` | Tests plus EXP001–EXP003 and figures. **~45 seconds** — this is the demo mode |
| `--skip-fetch` | Reuse the dataset already in `data/raw` |
| `--source mirror` | If the UCI archive is unreachable from your network |

`scripts/reproduce_all.sh` does the same thing if you prefer bash.

### Before you show anyone the numbers

Run this once:

```bash
python scripts/fetch_d2.py --source uci
```

Then open `configs/d2_diabetes.yaml` and change `provenance_status` from
`MIRROR_UNVERIFIED` to `UCI_VERIFIED`. Every result was produced from a mirrored copy of the
dataset that matched the published metadata exactly and matched the recorded SHA-256 — but
"verified against the canonical source" is a stronger statement than "verified against a
mirror", and your professor may well ask which one it is. Two minutes of work removes the
question.

### Where the outputs land

```
results/metrics/    one JSON per experiment — every number in the report comes from here
results/figures/    fig01-fig06, regenerated from those JSONs
results/models/     the frozen model and its model card
results/registry/   the assumption registry at each version
results/audit/      append-only audit log, one record per monitoring window
research/           the reports: start with final_report.md
```

---

## Part 2 — Showing it to your professor

### The one thing to get right

**The headline result is negative, and that is the contribution.** The composite score at the
centre of the framework showed no measurable detection advantage over simpler alternatives.

Do not present this apologetically, and do not bury it. A capstone that tested a framework
and found its central claim unsupported — with confidence intervals, controls, and an
ablation showing no component earns its place — is a stronger piece of work than one that
declared success. The failure mode to avoid is letting it *sound* like the project didn't
work. It worked; the framework didn't.

The line to have ready: *"I implemented the framework completely enough to test it, and
designed the experiments so they could show it was wrong. On this dataset, they did."*

### A 15-minute walkthrough

**1. The problem (1 min).** Healthcare ML models keep returning confident predictions after
the assumptions they were built on stop holding. The framework proposes monitoring those
assumptions and combining the signals into one score.

**2. The provenance finding (2 min).** Open `research/paper_analysis.md` §0. The composite
score, the A1–A4 taxonomy and every threshold appear in *neither* version of the source
paper. This was caught before any code was written, and it changed how everything is
labelled. It shows you read critically rather than implementing on trust — a good opening
because it is a finding about method, not about results.

**3. Live run (2 min).** `python scripts/reproduce_all.py --quick`. Let them watch 92 tests
pass and three experiments run. It ends with figures on disk. Nothing here is a slide of
claims; it is the thing actually executing.

**4. The results (6 min).** Four figures, in this order:

- **fig03 baseline ladder** — the answer to the main question. AHS 0.913 F1, the OR-rule
  0.898, best single monitor 0.889; bootstrap ΔF1 +0.025, 95% CI [0.000, 0.085]. One
  reclassified window moves F1 by 0.02, so the entire advantage is one window wide.
- **fig01 AHS stability** — 30 partitions of *unchanged* data. At small windows the score's
  own noise eats 82% of the governance band. This is why the threshold results need reading
  carefully, and it produces a usable rule: windows of roughly 10,000 rows.
- **fig04 OOD bake-off** — uncertainty-based detectors sit at chance (0.524 mean AUROC). On
  paediatric patients predictive entropy is *inverted* at 0.235: the model is most confident
  about the patients least represented in its training data. This one lands with clinicians.
- **fig05 severity ramp** — the score saturates: severity 0.5, 0.75 and 1.0 are
  indistinguishable once components pin at their ceiling.

**5. What did hold up (2 min).** Separating detection from governance prevented 7 of 10
inappropriate suspension recommendations on identical monitor output. The registry, the
audit trail and the monitors themselves are all fine. It is the aggregation that fails.

**6. Limitations, unprompted (2 min).** Say these before you are asked — it is the difference
between a defence and an interrogation. One dataset. No time axis, so detection speed is
untested. Injected ground truth, not clinical harm. 35 evaluation windows. Governance is
simulated with no human in it. All of it is in `final_report.md` §11.

### Questions you will get, and the honest answers

**"Isn't a negative result a failed project?"** No — the experiments were designed to be
capable of falsifying the framework, which is why the result means anything. The bootstrap
intervals, the null controls and the ablation are what make "no advantage" a finding rather
than an absence of evidence.

**"How do you know your implementation isn't just wrong?"** 92 tests, including analytic ones
with known answers — identical distributions give MMD → 0, perfect calibration gives
ECE → 0, AHS = 1 when nothing is violated. Plus a null control in every experiment: when
nothing has changed, the monitors stay quiet. And the positive control fires when a known
perturbation is injected.

**"Why this dataset?"** `research/dataset_selection.md` documents the alternatives and why
each was rejected. The honest version: credentialed datasets were ruled out, and among open
data no single source has both real timestamps and real EHR provenance. This one is a
genuine EHR extract with no time axis — which is exactly why detection speed is unanswered.

**"What would you do next?"** Get BRFSS, run the temporal replay, answer RQ2, and test the
window-size rule on a second substrate. `scripts/prepare_d1.py` is already written for it.

### If you have to submit something written

`research/final_report.md` is structured as a report already: methodology, data, setup,
baselines, results, statistical analysis, ablation, sensitivity, scalability, limitations,
conclusions, future work. Every number in it came from `results/`, so it stays true as long
as nobody edits it by hand. Convert it to PDF or Word and the figures drop in from
`results/figures/`.
