#!/bin/bash
# Neighborhood (nb_b030/nb_b050) + HPCC (hp_s3/s4/s5): 5 cells, STRICTLY
# SERIAL.  Idempotent via DONE markers; deletes nothing.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/stress_logs
mkdir -p "$LOG"

CELLS="st_2560 st_2555 st_2550"

disk_guard () {
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 2097152 ]; then
    echo "DISK_GUARD_FAIL: only $((avail_kb/1024)) MB free (< 2048 MB)."
    echo "Nothing is auto-deleted; free space manually and re-run."
    exit 2
  fi
}

for tag in $CELLS; do
  if [ -f "${tag}_out/DONE" ]; then
    echo "SKIP $tag (DONE present)"
    continue
  fi
  if [ ! -f "${tag}.txt" ]; then
    echo "FAIL $tag: config missing (run mk_stress.py first)"
    exit 3
  fi
  disk_guard
  mkdir -p "${tag}_out"
  echo "RUN  $tag  start=$(date '+%H:%M:%S')"
  s=$(date +%s)
  timeout -k 60 7200 "$BIN" "${tag}.txt" > "$LOG/${tag}.log" 2>&1
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
    echo "FAIL $tag rc=$rc $((e-s))s; log tail:"
    tail -5 "$LOG/${tag}.log"
    exit 5
  fi
done

echo "=== stress complete $(date) ==="
for tag in $CELLS; do
  [ -f "${tag}_out/DONE" ] && echo "  $tag DONE $(cat ${tag}_out/DONE)" \
    || echo "  $tag MISSING"
done
df -h /work | tail -1
touch "$LOG/ALL_DONE"
