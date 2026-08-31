"""Run every experiment in order, on any operating system.

    python scripts/reproduce_all.py

Same sequence as reproduce_all.sh, but pure Python so it works in Windows PowerShell and
the Command Prompt without bash, WSL or Git Bash. Stops at the first failure and says which
step failed, rather than continuing with a broken intermediate result.

    --skip-fetch     use the dataset already in data/raw
    --source mirror  fetch from the mirror instead of the canonical archive
    --quick          tests and EXP001–EXP003 only (~1 minute), for a demo
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FULL = [
    ("tests", [sys.executable, "-m", "pytest", "tests/", "-q"]),
    ("EXP001  pipeline, baselines, model freeze", [sys.executable, "scripts/run_g3.py"]),
    ("EXP002  monitors", [sys.executable, "scripts/run_g4.py"]),
    ("EXP003  AHS, triage, governance, audit", [sys.executable, "scripts/run_g5.py"]),
    ("EXP004-006  sensitivity, ladder, ablation", [sys.executable, "scripts/run_g6.py"]),
    ("EXP007-008  OOD bake-off, complete AHS", [sys.executable, "scripts/run_g7.py"]),
    ("EXP009-010  scalability, stability", [sys.executable, "scripts/run_g8.py"]),
    ("figures", [sys.executable, "scripts/make_figures.py"]),
]
QUICK = FULL[:4] + [FULL[-1]]


def run(label: str, cmd: list[str]) -> float:
    print(f"\n{'=' * 70}\n== {label}\n{'=' * 70}", flush=True)
    start = time.perf_counter()
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\nFAILED at: {label}\nCommand: {' '.join(cmd)}", file=sys.stderr)
        raise SystemExit(result.returncode)
    return time.perf_counter() - start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--source", choices=["uci", "mirror"], default="uci")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    steps = list(QUICK if args.quick else FULL)
    if not args.skip_fetch:
        steps.insert(0, ("data (downloads and verifies the checksum)",
                         [sys.executable, "scripts/fetch_d2.py", "--source", args.source]))

    timings = {}
    total = time.perf_counter()
    for label, cmd in steps:
        timings[label] = run(label, cmd)

    print(f"\n{'=' * 70}\nAll steps completed in {time.perf_counter() - total:.0f}s\n")
    for label, seconds in timings.items():
        print(f"   {seconds:7.1f}s  {label}")
    print("\nResults: results/metrics, results/figures, results/audit, results/registry")
    print("Report:  research/final_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
