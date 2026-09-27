#!/bin/bash
# Dual-bottleneck S6 at 200/400G: 8 algorithms x 2 rates (resumable, 2 workers).
set -u
SIM=/work/simulation; S6=/work/s6dual
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
cd $SIM
SHA=$(sha256sum build/scratch/third | awk "{print \$1}")
[ "$SHA" = "27c32a8f88faeac4606a8a9954deda8568532bdda09bc15293c7e27099a4bc79" ] \
  || { echo "WRONG BINARY $SHA"; exit 1; }

run_one(){
  local tag=$1 out=$S6/results/$1
  mkdir -p "$out"
  if [ -f "$out/.done" ]; then echo "[skip] $tag"; return 0; fi
  local t0=$(date +%s)
  timeout -k 60 7200 build/scratch/third $S6/configs/$tag.txt > $S6/logs/$tag.log 2>&1
  local rc=$?
  local n=$(awk "END{print NR-1}" $out/flow_timing.csv 2>/dev/null || echo 0)
  if [ $rc -eq 0 ] && [ "$n" -ge 60 ]; then
    echo "ok $(( $(date +%s) - t0 ))" > "$out/.done"
    echo "[done] $tag  $(( $(date +%s) - t0 ))s  incast_flows=$n"
  else
    echo "[FAIL] $tag rc=$rc flows=$n (log kept: logs/$tag.log)"
  fi
}
export -f run_one; export S6 SIM LD_LIBRARY_PATH

ls $S6/configs/fm*_s6_*.txt | sed "s#.*/##; s#\.txt##" | grep -vE "_(flow|sched|path|link)$" \
  | xargs -P 2 -I{} bash -c "run_one {}"

echo "== summarising =="
python3 /work/s6dual/summarize_s6.py
