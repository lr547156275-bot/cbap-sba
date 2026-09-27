#!/bin/bash
# Final 30-cell matrix.  STRICTLY SERIAL, cheap scenarios first so a platform
# failure costs the least-informative cells.  DONE markers make re-issuing
# this command resume at the first incomplete cell.  A failing cell is
# recorded and skipped, never silently retried; nothing is deleted.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/mx_logs
mkdir -p "$LOG"

SCEN="s1 s2 s6 s3 s4 s5"
ALGOS="dcqcn dctcp timely hpcc cbapsba"

disk_guard () {
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 1048576 ]; then
    echo "DISK_GUARD_FAIL: $((avail_kb/1024)) MB free (< 1024 MB); free space, re-run"
    exit 2
  fi
}

fails=""
for sc in $SCEN; do
  for algo in $ALGOS; do
    tag="mx_${sc}_${algo}"
    if [ -f "${tag}_out/DONE" ]; then
      echo "SKIP $tag"
      continue
    fi
    if [ ! -f "${tag}.txt" ]; then
      echo "FAIL $tag: config missing (run mk_matrix.py)"
      fails="$fails $tag"
      continue
    fi
    disk_guard
    mkdir -p "${tag}_out"
    echo "RUN  $tag  start=$(date '+%H:%M:%S')"
    s=$(date +%s)
    timeout -k 60 10800 "$BIN" "${tag}.txt" > "$LOG/${tag}.log" 2>&1
    rc=$?
    e=$(date +%s)
    if [ $rc -eq 0 ] && [ -s "${tag}_out/flow_summary.csv" ]; then
      echo "$rc $((e-s))" > "${tag}_out/DONE"
      echo "OK   $tag rc=$rc $((e-s))s"
    else
      echo "FAIL $tag rc=$rc $((e-s))s; tail:"
      tail -3 "$LOG/${tag}.log"
      fails="$fails $tag"
    fi
  done
  echo "--- scenario $sc finished $(date '+%H:%M:%S') ---"
done

echo "=== matrix complete $(date) ==="
echo "DONE: $(ls mx_*_out/DONE 2>/dev/null | wc -l)/30   FAILED:${fails:- none}"
df -h /work | tail -1
touch "$LOG/MATRIX_ALL_DONE"
