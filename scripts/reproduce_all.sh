#!/usr/bin/env bash
# Reproduce every experiment in order (BRIEF §21, §36).
# Each stage reads only what the previous one wrote; nothing is hand-edited between them.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== dependencies";           pip install -q -r requirements.txt
echo "== data (verifies sha256)"; python3 scripts/fetch_d2.py --source "${D2_SOURCE:-uci}"
echo "== tests";                  python3 -m pytest tests/ -q
echo "== EXP001  pipeline, baselines, freeze";        python3 scripts/run_g3.py
echo "== EXP002  monitors";                           python3 scripts/run_g4.py
echo "== EXP003  AHS, triage, governance, audit";     python3 scripts/run_g5.py
echo "== EXP004-006  sensitivity, ladder, ablation";  python3 scripts/run_g6.py
echo "== EXP007-008  OOD bake-off, full AHS";         python3 scripts/run_g7.py
echo "== EXP009-010  scalability, stability";         python3 scripts/run_g8.py
echo "== figures";                                    python3 scripts/make_figures.py
echo
echo "Done. Results in results/{metrics,models,registry,audit,figures}."
echo "D1 (BRFSS) is not included: download the annual files, then run scripts/prepare_d1.py."
