#!/bin/bash
# Run the four D arms, two at a time (the box has 2 cores and each ns-3 process
# saturates one).  Idempotent: a cell with a DONE marker is skipped, so this can
# be re-issued after a container restart and it resumes at the first incomplete
# arm.  ns-3 opens its outputs with "w", so a killed cell self-heals on rerun.
# Deletes nothing.
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/d1234_logs
mkdir -p "$LOG"

cell () {
  tag=$1
  if [ -f "${tag}_out/DONE" ]; then
    echo "SKIP $tag (DONE present)"
    return 0
  fi
  mkdir -p "${tag}_out"
  s=$(date +%s)
  "$BIN" "${tag}.txt" > "$LOG/${tag}.log" 2>&1
  rc=$?
  e=$(date +%s)
  if [ $rc -eq 0 ] && [ -s "${tag}_out/flow_summary.csv" ]; then
    echo "$rc $((e-s))" > "${tag}_out/DONE"
    echo "OK   $tag rc=$rc  $((e-s))s"
  else
    echo "FAIL $tag rc=$rc  $((e-s))s  (no DONE written)"
  fi
}

echo "=== wave 1: d1_dcqcn + d2_caponly  $(date) ==="
cell d1_dcqcn &
p1=$!
cell d2_caponly &
p2=$!
wait $p1 $p2

echo "=== wave 2: d3_capmig + d4_capmigband  $(date) ==="
cell d3_capmig &
p3=$!
cell d4_capmigband &
p4=$!
wait $p3 $p4

echo "=== all waves finished $(date) ==="
for t in d1_dcqcn d2_caponly d3_capmig d4_capmigband; do
  if [ -f "${t}_out/DONE" ]; then
    echo "  $t DONE $(cat ${t}_out/DONE)"
  else
    echo "  $t MISSING DONE"
  fi
done
df -h /work | tail -1
touch "$LOG/ALL_DONE"
