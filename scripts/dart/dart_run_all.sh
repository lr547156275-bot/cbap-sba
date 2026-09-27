#!/bin/bash
# DART-RA batch: regression re-gate under the FINAL binary, then all 15 cells
# (2 workers, resumable), then comparison vs the old seed=2 matrix.
set -u
SIM=/work/simulation
D=/work/dart
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
BIN=$SIM/build/scratch/third
echo "binary: $(sha256sum $BIN | awk '{print $1}')"

echo "== 1. regression re-gate (final binary vs frozen results) =="
for base in fm400g_s2_cbap fm400g_s2_dcqn; do
  R=$D/regression/final_$base
  mkdir -p "$R"
  sed "s#/work/v2_400g/results/$base#$R#g" /work/v2_400g/configs/$base.txt > $R/cfg.txt
  timeout -k 60 3600 $BIN $R/cfg.txt > $R/run.log 2>&1 || { echo "REGRESSION RUN FAIL $base"; exit 1; }
  bad=0; n=0
  for f in $R/*.csv; do
    b=$(basename "$f"); o=/work/v2_400g/results/$base/$b
    [ -f "$o" ] || continue
    n=$((n+1)); cmp -s "$f" "$o" || { bad=$((bad+1)); echo "  DIFFERS: $base/$b"; }
  done
  echo "$base: identical $((n-bad))/$n"
  [ $bad -ne 0 ] && { echo "REGRESSION GATE FAIL"; exit 1; }
done
echo "REGRESSION GATE PASS (final binary)"

echo "== 2. run all DART cells (2 workers, resumable) =="
run_one() {
  local tag=$1
  local out=$D/results/$tag
  if [ -f "$out/STATUS" ] && grep -q "^ok" "$out/STATUS"; then echo "SKIP $tag"; return 0; fi
  mkdir -p "$out"
  local s e rc got want
  want=64; case "$tag" in *_s5) want=32;; esac
  s=$(date +%s)
  timeout -k 60 7200 $BIN $D/configs/$tag.txt > $D/logs/$tag.log 2>&1
  rc=$?; e=$(date +%s)
  got=$(awk 'END{print NR-1}' "$out/flow_timing.csv" 2>/dev/null || echo 0)
  if [ $rc -eq 0 ] && [ "$got" = "$want" ]; then
    echo "ok $((e-s))" > "$out/STATUS"; echo "OK   $tag $((e-s))s"
  else
    echo "fail_rc $rc flows=$got/$want $((e-s))" > "$out/STATUS"; echo "FAIL $tag rc=$rc flows=$got/$want"
  fi
}
TAGS=$(ls $D/configs/dart*.txt | xargs -n1 basename | sed 's/.txt//')
pids=()
for t in $TAGS; do
  run_one "$t" &
  pids+=($!)
  if [ ${#pids[@]} -ge 2 ]; then wait "${pids[0]}"; pids=("${pids[@]:1}"); fi
done
for p in "${pids[@]}"; do wait "$p"; done

echo "== 3. comparison vs old seed=2 matrix =="
python3 $D/dart_compare.py
echo "DART_BATCH_DONE"
