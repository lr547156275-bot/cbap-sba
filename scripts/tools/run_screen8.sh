#!/bin/bash
# D4v2 screening matrix: 7 cells, STRICTLY SERIAL (MAX_JOBS=1 by construction:
# no '&' anywhere).  Idempotent: a cell with a DONE marker is skipped, so after
# any interruption re-issuing the same command resumes at the first incomplete
# cell.  ns-3 opens outputs with "w", so a killed cell self-heals on rerun.
# Deletes nothing, overwrites no existing result directory.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/screen8_logs
mkdir -p "$LOG"

CELLS="scr8_d1 scr8_d3 scr8_b005 scr8_b010 scr8_b020 scr8_b040 scr8_b080"

disk_guard () {
  # fail-fast below 2 GB free; never deletes anything
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 2097152 ]; then
    echo "DISK_GUARD_FAIL: only $((avail_kb/1024)) MB free on /work (< 2048 MB)"
    echo "Free space manually (nothing is auto-deleted), then re-run."
    exit 2
  fi
}

for tag in $CELLS; do
  if [ -f "${tag}_out/DONE" ]; then
    echo "SKIP $tag (DONE present)"
    continue
  fi
  if [ ! -f "${tag}.txt" ]; then
    echo "FAIL $tag: config ${tag}.txt missing (run mk_screen8.py first)"
    exit 3
  fi
  disk_guard
  mkdir -p "${tag}_out"
  echo "RUN  $tag  start=$(date '+%H:%M:%S')"
  s=$(date +%s)
  timeout -k 60 3600 "$BIN" "${tag}.txt" > "$LOG/${tag}.log" 2>&1
  rc=$?
  e=$(date +%s)
  if grep -q "CONFIG_ERROR" "$LOG/${tag}.log"; then
    echo "FAIL $tag rc=$rc $((e-s))s CONFIG_ERROR:"
    grep "CONFIG_ERROR" "$LOG/${tag}.log" | head -3
    exit 4
  fi
  if [ $rc -eq 0 ] && [ -s "${tag}_out/flow_summary.csv" ]; then
    echo "$rc $((e-s))" > "${tag}_out/DONE"
    echo "OK   $tag rc=$rc $((e-s))s"
  else
    echo "FAIL $tag rc=$rc $((e-s))s (no DONE written; log tail:)"
    tail -5 "$LOG/${tag}.log"
    exit 5
  fi
done

echo "=== screen8 complete $(date) ==="
for tag in $CELLS; do
  if [ -f "${tag}_out/DONE" ]; then
    echo "  $tag DONE $(cat ${tag}_out/DONE)"
  else
    echo "  $tag MISSING"
  fi
done
df -h /work | tail -1
touch "$LOG/ALL_DONE"
