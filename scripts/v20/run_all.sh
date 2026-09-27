#!/bin/bash
# V20 batch-1 driver: gated, resumable.  Run inside the hpcc-build container:
#   bash /work/v20/scripts/run_all.sh
set -u
ROOT=/work/v20
S=$ROOT/scripts
mkdir -p $ROOT/logs $ROOT/docs
exec > >(tee -a $ROOT/logs/driver.log) 2>&1
echo "########## V20 driver start $(date -u +%FT%TZ) ##########"

echo "== STEP 1: plan + configs (drift-checked) =="
python3 $S/gen_plan.py || { echo "ABORT: plan generation failed"; exit 1; }

echo "== STEP 2: seed=2 replays (20) for the reuse audit =="
bash $S/run_batch.sh '_(cbap|hpcc|dcqn|dctcp|timely)_s2_a1$' 2
python3 $S/replay_audit.py
REPLAY_RC=$?
if [ $REPLAY_RC -ne 0 ]; then
  echo "GATE: replay audit FAILED - old seed2 will NOT be pooled."
  echo "Per task book: keep old results, run seeds 1-5 fresh on this build."
  echo "(seed2 replays already exist and become the seed2 cells.)"
fi

echo "== STEP 3: B-group seed=2 semantic gate =="
bash $S/run_batch.sh '(no_migration|no_phase_spread)_s2_a1$' 2
python3 $S/bvariant_check.py || { echo "ABORT: B-variant semantics failed - variants marked 待确认, not continuing their seeds"; BVAR_FAIL=1; }

echo "== STEP 4: remaining seeds (A 1/3/4/5 + B 1/3/4/5) =="
if [ "${BVAR_FAIL:-0}" = "1" ]; then
  bash $S/run_batch.sh '^[24]00g_s[235]*_(cbap|hpcc|dcqn|dctcp|timely)_s[1345]_a1$' 2
else
  bash $S/run_batch.sh '_s[1345]_a1$' 2
fi

echo "== STEP 5: statistics + C-item + figure2 search + verification =="
python3 $S/stats_v20.py
python3 $S/organize_c.py
bash $S/find_figure2.sh
python3 $S/verify_all.py || echo "NOTE: verify_all reported required failures - see validation/checks.json (kept, not hidden)"

echo "== STEP 6: bundle + zip + self-check =="
bash $S/make_zip.sh

echo "########## V20 driver done $(date -u +%FT%TZ) ##########"
