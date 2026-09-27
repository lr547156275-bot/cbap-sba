#!/bin/bash
# S4/S5 held-out validation: 6 cells, STRICTLY SERIAL (no '&').  Idempotent
# via DONE markers; re-issuing the same command resumes at the first
# incomplete cell.  Deletes nothing, overwrites no existing result directory.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/s45_logs
mkdir -p "$LOG"

CELLS="s4v_d1 s4v_d3 s4v_b040 s5v_d1 s5v_d3 s5v_b040"

disk_guard () {
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 2097152 ]; then
    echo "DISK_GUARD_FAIL: only $((avail_kb/1024)) MB free on /work (< 2048 MB)"
    echo "Nothing is auto-deleted.  Free space manually, then re-run this"
    echo "command; completed cells are skipped via their DONE markers."
    exit 2
  fi
}

for tag in $CELLS; do
  if [ -f "${tag}_out/DONE" ]; then
    echo "SKIP $tag (DONE present)"
    continue
  fi
  if [ ! -f "${tag}.txt" ]; then
    echo "FAIL $tag: config missing (run mk_s45.py first)"
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

echo "=== s45 complete $(date) ==="
for tag in $CELLS; do
  [ -f "${tag}_out/DONE" ] && echo "  $tag DONE $(cat ${tag}_out/DONE)" \
    || echo "  $tag MISSING"
done
df -h /work | tail -1
touch "$LOG/ALL_DONE"
