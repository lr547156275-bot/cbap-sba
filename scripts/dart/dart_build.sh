#!/bin/bash
# DART-RA: patch, build (with original-binary protection), regression-gate,
# generate the 15 configs, smoke one cell.  Run inside hpcc-build.
set -u
SIM=/work/simulation
D=/work/dart
mkdir -p $D/{configs,results,logs,regression}
cd $SIM

echo "== 0. protect the frozen binary =="
mkdir -p /work/binaries
if [ ! -f /work/binaries/third_orig_22921aa9 ]; then
  cp build/scratch/third /work/binaries/third_orig_22921aa9
fi
sha256sum /work/binaries/third_orig_22921aa9

echo "== 1. work on a dedicated branch =="
git rev-parse --abbrev-ref HEAD
git checkout -B dart-ra-baseline 2>&1 | tail -1

echo "== 2. apply patch =="
python3 /work/dart/apply_dart_patch.py || { echo PATCH_FAILED; exit 1; }
git diff --stat | tail -5

echo "== 3. incremental build =="
./waf build > $D/logs/build.log 2>&1
RC=$?
tail -5 $D/logs/build.log
[ $RC -ne 0 ] && { echo BUILD_FAILED; grep -iE "error" $D/logs/build.log | head -10; exit 1; }
NEWSHA=$(sha256sum build/scratch/third | awk '{print $1}')
echo "new binary: $NEWSHA"

echo "== 4. regression gate: old modes must be byte-identical =="
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
for base in fm400g_s2_cbap fm400g_s2_dcqn; do
  R=$D/regression/$base
  mkdir -p "$R"
  sed "s#/work/v2_400g/results/$base#$R#g" /work/v2_400g/configs/$base.txt > $R/cfg.txt
  timeout -k 60 3600 build/scratch/third $R/cfg.txt > $R/run.log 2>&1 || { echo "REGRESSION RUN FAIL $base"; exit 1; }
  bad=0; n=0
  for f in $R/*.csv; do
    b=$(basename "$f"); o=/work/v2_400g/results/$base/$b
    [ -f "$o" ] || continue
    n=$((n+1)); cmp -s "$f" "$o" || { bad=$((bad+1)); echo "  DIFFERS: $base/$b"; }
  done
  echo "$base: identical $((n-bad))/$n"
  [ $bad -ne 0 ] && { echo "REGRESSION GATE FAIL - existing modes perturbed"; exit 1; }
done
echo "REGRESSION GATE PASS - existing CC modes byte-identical under the new binary"

echo "== 5. generate 15 DART-RA configs (clone dcqn templates, S1-S5 x 3 rates) =="
# DART parameter block appended to every config (defaults; user will tune)
DARTKEYS="CC_MODE 40
DART_ALPHA 0.95
DART_ACTIVE_TIMEOUT_US 100
DART_UPDATE_MIN_INTERVAL_US 10
DART_CTRL_DELAY_US 6
DART_ORACLE_N 0
DART_MIN_RATE_MBPS 100"
for rate in 10 200 400; do
  for s in s1 s2 s3 s4 s5; do
    src=/work/v2_400g/configs/fm${rate}g_${s}_dcqn.txt
    tag=dart_${rate}g_${s}
    out=$D/results/$tag
    mkdir -p "$out"
    # clone; drop the CC_MODE line; retarget outputs; rename scenario
    sed -e "s#/work/v2_400g/results/fm${rate}g_${s}_dcqn#$out#g" \
        -e "/^CC_MODE /d" \
        -e "s/^SCENARIO .*/SCENARIO ${tag}/" \
        -e "s/^ALGORITHM .*/ALGORITHM dart_ra/" \
        "$src" > $D/configs/$tag.txt
    printf '%s\n' "$DARTKEYS" >> $D/configs/$tag.txt
    # drift check: vs parent, only allowed keys differ
    stray=$(diff "$src" $D/configs/$tag.txt | grep '^[<>]' \
      | grep -vE "CC_MODE|DART_|SCENARIO|ALGORITHM|$out|results/fm${rate}g_${s}_dcqn") || true
    [ -z "$stray" ] || { echo "CONFIG DRIFT in $tag:"; echo "$stray"; exit 7; }
  done
done
echo "15 configs generated + drift-checked"

echo "== 6. smoke: dart_400g_s2 =="
T=$D/results/dart_400g_s2
timeout -k 60 3600 build/scratch/third $D/configs/dart_400g_s2.txt > $D/logs/dart_400g_s2.log 2>&1
RC=$?
flows=$(awk 'END{print NR-1}' $T/flow_timing.csv 2>/dev/null || echo 0)
echo "smoke rc=$RC flows=$flows/64"
grep -m3 "DART_" $D/logs/dart_400g_s2.log
if [ $RC -eq 0 ] && [ "$flows" = "64" ]; then
  python3 - <<'PY'
import csv, math
rows=list(csv.DictReader(open("/work/dart/results/dart_400g_s2/flow_timing.csv")))
f=[(int(r["last_ack_ns"])-int(r["first_data_tx_ns"])) for r in rows if 1<=int(r["flow_id"])<=64]
last=[int(r["last_ack_ns"]) for r in rows if 1<=int(r["flow_id"])<=64]
f.sort()
print("SMOKE dart_400g_s2: CCT=%.3f ms  meanFCT=%.3f ms  p99FCT=%.3f ms"
      % ((max(last)-20000000)/1e6, sum(f)/len(f)/1e6,
         f[max(0,math.ceil(0.99*len(f))-1)]/1e6))
print("(reference: dcqn 6.50ms / cbap 5.88ms / timely 5.73ms CCT at 400g_s2)")
PY
else
  tail -5 $D/logs/dart_400g_s2.log
fi
echo "== done: binary=$NEWSHA (original preserved at /work/binaries/third_orig_22921aa9) =="
