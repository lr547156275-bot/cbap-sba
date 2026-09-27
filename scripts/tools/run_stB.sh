#!/bin/bash
# Option-A round: 2 byte-regression cells + 3 stress probes, STRICTLY SERIAL.
# HARD RULE: if either regression cell differs from its frozen scr8 twin on
# ANY result file, STOP before running a single stress cell.
set -u
cd /work/simulation/experiment/scheme1_sba || exit 1
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
BIN=/work/simulation/build/scratch/third
LOG=/work/stress_logs
mkdir -p "$LOG"

disk_guard () {
  avail_kb=$(df --output=avail /work | tail -1 | tr -d ' ')
  if [ "$avail_kb" -lt 1572864 ]; then
    echo "DISK_GUARD_FAIL: $((avail_kb/1024)) MB free (< 1536 MB); free space and re-run"
    exit 2
  fi
}

run_cell () {
  tag=$1
  if [ -f "${tag}_out/DONE" ]; then
    echo "SKIP $tag"
    return 0
  fi
  disk_guard
  mkdir -p "${tag}_out"
  echo "RUN  $tag  start=$(date '+%H:%M:%S')"
  s=$(date +%s)
  timeout -k 60 7200 "$BIN" "${tag}.txt" > "$LOG/${tag}.log" 2>&1
  rc=$?
  e=$(date +%s)
  echo "$rc $((e-s))" > "${tag}_out/RC"
  if [ $rc -eq 0 ] && [ -s "${tag}_out/flow_summary.csv" ]; then
    echo "$rc $((e-s))" > "${tag}_out/DONE"
    echo "OK   $tag rc=$rc $((e-s))s"
    return 0
  fi
  echo "FAIL $tag rc=$rc $((e-s))s; tail:"
  tail -4 "$LOG/${tag}.log"
  return 1
}

# ---- phase 1: byte regression ---------------------------------------------
for pair in "reg_d3 scr8_d3" "reg_b040 scr8_b040"; do
  set -- $pair
  new=$1; ref=$2
  run_cell "$new" || { echo "REGRESSION CELL FAILED -- STOP"; exit 3; }
  bad=0
  for f in flow_summary.csv port_summary.csv selected_link_timeseries.csv \
           qlen.txt tx_serialization.csv pfc_events.csv round_summary.csv \
           admission.csv sba_events.csv rate_transition.csv; do
    a=$(sha256sum "${ref}_out/$f" 2>/dev/null | cut -c1-16)
    b=$(sha256sum "${new}_out/$f" 2>/dev/null | cut -c1-16)
    if [ "$a" = "$b" ]; then
      echo "  identical  $new/$f"
    else
      echo "  DIFFERS    $new/$f  ($a vs $b)"
      bad=1
    fi
  done
  if [ $bad -ne 0 ]; then
    echo "BYTE_REGRESSION_FAIL: $new differs from frozen $ref -- the bound fix"
    echo "is NOT inert.  STOPPING before any stress cell.  Report this."
    exit 4
  fi
  echo "REGRESSION OK: $new byte-identical to frozen $ref"
done

# ---- phase 2: stress probes (expected to ADMIT now) ------------------------
for tag in st_2560 st_2555 st_2550; do
  rm -f "${tag}_out/DONE"        # previous aborted partials must re-run
  if run_cell "$tag"; then
    grep -m1 "SBA_LIFECYCLE_CHECK batch=2" "$LOG/${tag}.log" || true
  else
    echo "STRESS CELL $tag failed; log kept at $LOG/${tag}.log -- continuing"
    grep -E "SBA_LIFECYCLE_CHECK batch=2|violates" "$LOG/${tag}.log" | tail -2
  fi
done

echo "=== stB complete $(date) ==="
ls -la st_*_out/DONE reg_*_out/DONE 2>/dev/null
df -h /work | tail -1
touch "$LOG/STB_ALL_DONE"
