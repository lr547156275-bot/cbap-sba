#!/bin/bash
# M campaign runner: 24 cells (m1-m4 x 6 algs), 2 workers, resumable.
set -u
SIM=/work/simulation; M=/work/mdeep
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
cd $SIM
WANT=$(cat $M/BINARY_SHA 2>/dev/null || echo none)
SHA=$(sha256sum build/scratch/third | awk '{print $1}')
[ "$SHA" = "$WANT" ] || { echo "WRONG BINARY $SHA (want $WANT)"; exit 1; }

run_one(){
  local tag=$1 out=$M/results/$1
  mkdir -p "$out"
  if [ -f "$out/.done" ]; then echo "[skip] $tag"; return 0; fi
  local t0=$(date +%s)
  timeout -k 60 7200 build/scratch/third $M/configs/$tag.txt > $M/logs/$tag.log 2>&1
  local rc=$?
  local n=$(awk 'END{print NR-1}' $out/flow_timing.csv 2>/dev/null || echo 0)
  local want=60
  case "$tag" in m4_*) want=52;; esac
  if [ $rc -eq 0 ] && [ "$n" -ge "$want" ]; then
    echo "ok $(( $(date +%s) - t0 ))" > "$out/.done"
    echo "[done] $tag  $(( $(date +%s) - t0 ))s  incast=$n"
  else
    echo "[FAIL] $tag rc=$rc flows=$n/$want (log kept)"
  fi
}
export -f run_one; export M SIM LD_LIBRARY_PATH

ls $M/configs/m*_400g_*.txt | sed 's#.*/##; s#\.txt##' \
  | grep -vE '_(flow|sched|path|link)$' | xargs -P 2 -I{} bash -c 'run_one {}'

echo "== summarising =="
python3 /work/mdeep/summarize_m.py
