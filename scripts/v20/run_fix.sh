#!/bin/bash
# V20 remediation driver: seed-1 guard handling + B-gate recheck + finish.
set -u
ROOT=/work/v20
S=$ROOT/scripts
exec > >(tee -a $ROOT/logs/driver.log) 2>&1
echo "########## V20 FIX driver start $(date -u +%FT%TZ) ##########"

echo "== FIX 0: packet-trace code audit (recording-only?) =="
cd /work/simulation
grep -n "cbap_packet_trace" scratch/third.cc | head -6
grep -rn "packetTrace\|PacketTrace" src/point-to-point/model/rdma-hw.cc | head -8
echo "(full audit note goes into validation/logging_equivalence.csv)"

echo "== FIX 1: logging-equivalence run (seed=3 cell + packet-trace keys) =="
EQ=$ROOT/results_eqcheck
mkdir -p $EQ
sed -e "s#$ROOT/results/400g_s2_cbap_s3_a1#$EQ#g" \
    $ROOT/configs/400g_s2_cbap_s3_a1.txt > $EQ/cfg.txt
echo "CBAP_PACKET_TRACE_FILE $EQ/cbap_packet_trace.bin" >> $EQ/cfg.txt
echo "CBAP_PACKET_TRACE_MAX_MB 64" >> $EQ/cfg.txt
export LD_LIBRARY_PATH=/work/simulation/build:${LD_LIBRARY_PATH:-}
timeout -k 60 5400 /work/simulation/build/scratch/third $EQ/cfg.txt \
    > $EQ/stdout.log 2> $EQ/stderr.log
RC=$?
echo "equivalence run rc=$RC"
n=0; same=0; diff=0
{
  echo "file,verdict"
  for f in $EQ/*.csv; do
    b=$(basename "$f")
    o=$ROOT/results/400g_s2_cbap_s3_a1/$b
    [ -f "$o" ] || continue
    n=$((n+1))
    if cmp -s "$f" "$o"; then same=$((same+1)); echo "$b,IDENTICAL"
    else diff=$((diff+1)); echo "$b,DIFFERS"; fi
  done
  echo "packet_trace_size_bytes,$(stat -c%s $EQ/cbap_packet_trace.bin 2>/dev/null || echo 0)"
} > $ROOT/validation/logging_equivalence.csv
cat $ROOT/validation/logging_equivalence.csv
if [ $RC -ne 0 ] || [ $diff -ne 0 ] || [ $same -eq 0 ]; then
  echo "GATE: logging-equivalence FAILED - seed=1 stays blocked; record and stop"
  exit 1
fi
echo "GATE: logging-equivalence PASS ($same/$n identical) - packet trace is behaviour-neutral"

echo "== FIX 2: archive the failed seed-1 first attempts =="
mkdir -p $ROOT/failed_attempts
for d in $ROOT/results/*_s1_a1; do
  [ -f "$d/STATUS" ] || continue
  if grep -q "^fail" "$d/STATUS"; then
    mv "$d" "$ROOT/failed_attempts/$(basename $d).attempt1"
    echo "archived $(basename $d).attempt1"
  fi
done

echo "== FIX 3: regenerate plan/configs (seed-1 gets bounded packet-trace keys) =="
python3 $S/gen_plan.py || exit 1

echo "== FIX 4: B-variant gate recheck (calibrated evidence) =="
python3 $S/bvariant_check.py || { echo "ABORT: B gate still failing"; exit 1; }

echo "== FIX 5: run remaining cells (A s1 x20 + B s1 x4 + B s3/s4/s5 x12) =="
bash $S/run_batch.sh '_s1_a1$' 2
bash $S/run_batch.sh '(no_migration|no_phase_spread)_s[345]_a1$' 2

echo "== FIX 6: stats + verify + bundle =="
python3 $S/stats_v20.py
python3 $S/organize_c.py
python3 $S/verify_all.py || echo "NOTE: verify_all failures recorded in checks.json"
bash $S/make_zip.sh

echo "########## V20 FIX driver done $(date -u +%FT%TZ) ##########"
