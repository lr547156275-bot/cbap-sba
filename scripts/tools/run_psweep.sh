#!/bin/bash
# Neighborhood (nb_b030/nb_b050) + HPCC (hp_s3/s4/s5): 5 cells, STRICTLY
# SERIAL.  Idempotent via DONE markers; deletes nothing.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/pw_logs
mkdir -p "$LOG"

CELLS="pw_dcqcn_k200 pw_dcqcn_k800 pw_dcqcn_k1600 pw_dcqcn_pmax10 pw_dctcp_k200 pw_dctcp_k800 pw_dctcp_k1600 pw_dctcp_ai500 pw_hpcc_u90 pw_hpcc_u98 pw_hpcc_mi1 pw_timely_ai25 pw_timely_ai100 pw_timely_ai200"

disk_guard () {
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 1048576 ]; then
    echo "DISK_GUARD_FAIL: only $((avail_kb/1024)) MB free (< 1024 MB)."
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
    echo "FAIL $tag: config missing (run mk_psweep.py first)"
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
    continue  # shakedown: a failing cell is a finding, not a stop
  fi
  if [ $rc -eq 0 ] && [ -s "${tag}_out/flow_summary.csv" ]; then
    echo "$rc $((e-s))" > "${tag}_out/DONE"
    echo "OK   $tag rc=$rc $((e-s))s"
  else
    echo "FAIL $tag rc=$rc $((e-s))s; log tail:"
    tail -5 "$LOG/${tag}.log"
    continue  # shakedown: record and move on
  fi
done

echo "=== psweep complete $(date) ==="
for tag in $CELLS; do
  [ -f "${tag}_out/DONE" ] && echo "  $tag DONE $(cat ${tag}_out/DONE)" \
    || echo "  $tag MISSING"
done
df -h /work | tail -1
touch "$LOG/ALL_DONE"
