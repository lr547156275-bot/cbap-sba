#!/bin/bash
# V20 limited-list runner: 2-worker pool, resumable, failure-retaining.
#   usage: run_batch.sh <filter-regex-on-run_id> [workers]
# Each attempt writes results/<run_id>/STATUS:
#   ok <wall_s> | fail_rc <rc> <wall_s> | fail_flows <got>/<want> <wall_s>
# Existing STATUS beginning with "ok" -> skipped (resume).  Failures keep
# every partial output and log; they are never deleted or retried silently.
set -u
BIN=/work/simulation/build/scratch/third
ROOT=/work/v20
PLAN=$ROOT/plan/run_plan.csv
FILTER=${1:-.}
WORKERS=${2:-2}
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}

run_one() {
  local run_id=$1 cfg=$2 want=$3
  local out=$ROOT/results/$run_id
  if [ -f "$out/STATUS" ] && grep -q "^ok" "$out/STATUS"; then
    echo "SKIP $run_id (ok)"; return 0
  fi
  local free
  free=$(df -BG /work | awk 'NR==2{gsub("G","",$4); print $4}')
  if [ "$free" -lt 3 ]; then
    echo "DISK_GUARD $run_id (${free}G free) -- stopping this worker"
    return 9
  fi
  mkdir -p "$out"
  local s e rc got
  s=$(date +%s)
  timeout -k 60 5400 "$BIN" "$cfg" > "$out/stdout.log" 2> "$out/stderr.log"
  rc=$?
  e=$(date +%s)
  got=$(awk 'END{print NR-1}' "$out/flow_timing.csv" 2>/dev/null || echo 0)
  if [ "$rc" -ne 0 ]; then
    echo "fail_rc $rc $((e-s))" > "$out/STATUS"
    echo "FAIL $run_id rc=$rc $((e-s))s"
  elif [ "$got" != "$want" ]; then
    echo "fail_flows $got/$want $((e-s))" > "$out/STATUS"
    echo "FAIL $run_id flows=$got/$want $((e-s))s"
  else
    echo "ok $((e-s))" > "$out/STATUS"
    echo "OK   $run_id $((e-s))s"
  fi
  return 0
}

# build the task list from the plan (skip header), apply filter
mapfile -t TASKS < <(awk -F, -v flt="$FILTER" 'NR>1 && $1 ~ flt {print $1" "$9" "$11}' "$PLAN")
echo "runner: ${#TASKS[@]} tasks match filter [$FILTER], workers=$WORKERS"

i=0
pids=()
for t in "${TASKS[@]}"; do
  set -- $t
  run_one "$1" "$2" "$3" &
  pids+=($!)
  i=$((i+1))
  if [ "${#pids[@]}" -ge "$WORKERS" ]; then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done
for p in "${pids[@]}"; do wait "$p"; done

echo "=== runner summary ==="
ok=0; fail=0
for t in "${TASKS[@]}"; do
  set -- $t
  st=$(head -1 "$ROOT/results/$1/STATUS" 2>/dev/null || echo missing)
  case "$st" in ok*) ok=$((ok+1));; *) fail=$((fail+1)); echo "  NOT-OK $1: $st";; esac
done
echo "ok=$ok not_ok=$fail of ${#TASKS[@]}"
