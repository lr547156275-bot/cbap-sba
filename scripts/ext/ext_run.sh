#!/bin/bash
# E1/E2/E3 extension campaign runner: 18 cells, 2 workers, resumable.
set -u
SIM=/work/simulation; X=/work/ext
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
cd $SIM
WANT=$(cat $X/BINARY_SHA 2>/dev/null || echo none)
SHA=$(sha256sum build/scratch/third | awk '{print $1}')
[ "$SHA" = "$WANT" ] || { echo "WRONG BINARY $SHA (want $WANT)"; exit 1; }

run_one(){
  local tag=$1 out=$X/results/$1
  mkdir -p "$out"
  if [ -f "$out/.done" ]; then echo "[skip] $tag"; return 0; fi
  local t0=$(date +%s)
  timeout -k 60 7200 build/scratch/third $X/configs/$tag.txt > $X/logs/$tag.log 2>&1
  local rc=$?
  local n=$(awk 'END{print NR-1}' $out/flow_timing.csv 2>/dev/null || echo 0)
  if [ $rc -eq 0 ] && [ "$n" -ge 1 ]; then
    echo "ok $(( $(date +%s) - t0 ))" > "$out/.done"
    echo "[done] $tag  $(( $(date +%s) - t0 ))s  flows=$n"
  else
    echo "[FAIL] $tag rc=$rc flows=$n (log kept)"
  fi
}
export -f run_one; export X SIM LD_LIBRARY_PATH

ls $X/configs/e*_400g_*.txt | sed 's#.*/##; s#\.txt##' \
  | grep -vE '_(flow|sched|path|link|fixedpath)$' | xargs -P 2 -I{} bash -c 'run_one {}'

echo "== summarising =="
python3 /work/ext/summarize_ext.py
