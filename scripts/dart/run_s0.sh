#!/bin/bash
set -u
SIM=/work/simulation; D=/work/dart
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
cd $SIM
SHA=$(sha256sum build/scratch/third | awk "{print \$1}")
[ "$SHA" = "27c32a8f88faeac4606a8a9954deda8568532bdda09bc15293c7e27099a4bc79" ] || { echo "WRONG BINARY $SHA"; exit 1; }
for tag in dartv2_10g_s0 dartv2_200g_s0 dartv2_400g_s0; do
  out=$D/results/$tag; mkdir -p "$out"
  [ -f "$out/STATUS" ] && { echo "[skip] $tag"; continue; }
  t0=$(date +%s)
  timeout -k 60 7200 build/scratch/third $D/configs/$tag.txt > $D/logs/$tag.log 2>&1
  rc=$?
  n=$(awk "END{print NR-1}" $out/flow_timing.csv 2>/dev/null || echo 0)
  if [ $rc -eq 0 ] && [ "$n" -ge 64 ]; then
    echo "ok $(( $(date +%s) - t0 ))" > "$out/STATUS"
    echo "[done] $tag $(( $(date +%s) - t0 ))s flows=$n"
  else
    echo "[FAIL] $tag rc=$rc flows=$n"
  fi
done
echo "== s0 comparison =="
python3 - <<"PY"
import csv,math,os
def m(d,lo,hi):
    ft=d+"/flow_timing.csv"
    if not os.path.isfile(ft): return None
    inc=[];last=[]
    for x in csv.DictReader(open(ft)):
        fid=int(x["flow_id"])
        if lo<=fid<=hi:
            inc.append(int(x["last_ack_ns"])-int(x["first_data_tx_ns"]))
            last.append(int(x["last_ack_ns"]))
    if not inc: return None
    inc.sort()
    q=max(int(r["selected_link_peak_queue"]) for r in csv.DictReader(open(d+"/round_summary.csv")))
    pfc=open(d+"/pfc_events.csv").read().count("\n")-1
    return ((max(last)-20000000)/1e6,sum(inc)/len(inc)/1e6,
            inc[max(0,math.ceil(0.99*len(inc))-1)]/1e6,q/1e6,pfc,len(inc))
print("%-10s %-7s %9s %9s %9s %8s %5s"%("case","alg","CCT","meanFCT","p99FCT","qpk_MB","PFC"))
for rate in ("10","200","400"):
    for alg in ("cbap","hpcc","dcqn","dctcp","timely"):
        r=m("/work/v2_400g/results/fm%sg_s0_%s"%(rate,alg),1,64)
        if r: print("%-10s %-7s %9.3f %9.3f %9.3f %8.3f %5d"%(rate+"g_s0",alg,*r[:5]))
    r=m("/work/dart/results/dartv2_%sg_s0"%rate,1,64)
    if r: print("%-10s %-7s %9.3f %9.3f %9.3f %8.3f %5d"%(rate+"g_s0","dart",*r[:5]))
    else: print("%-10s dart MISSING"%(rate+"g_s0"))
PY
