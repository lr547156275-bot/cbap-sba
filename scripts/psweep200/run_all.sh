#!/bin/bash
# 200G S5 parameter sweep: eta x4, lease x4, bmax x9 (resumable, 2 workers).
set -u
SIM=/work/simulation; P=/work/psweep200
export LD_LIBRARY_PATH=$SIM/build:${LD_LIBRARY_PATH:-}
cd $SIM

# integrity: refuse to run under a wrong binary
SHA=$(sha256sum build/scratch/third | awk "{print \$1}")
[ "$SHA" = "27c32a8f88faeac4606a8a9954deda8568532bdda09bc15293c7e27099a4bc79" ] \
  || { echo "WRONG BINARY $SHA"; exit 1; }

run_one(){
  local tag=$1
  local out=$P/results/$tag
  mkdir -p "$out"
  if [ -f "$out/.done" ]; then echo "[skip] $tag"; return 0; fi
  local t0=$(date +%s)
  timeout -k 60 7200 build/scratch/third $P/configs/$tag.txt \
    > $P/logs/$tag.log 2>&1
  local rc=$?
  local n=$(awk "END{print NR-1}" $out/flow_timing.csv 2>/dev/null || echo 0)
  if [ $rc -eq 0 ] && [ "$n" -ge 32 ]; then
    echo "ok $(( $(date +%s) - t0 ))" > "$out/.done"
    echo "[done] $tag  $(( $(date +%s) - t0 ))s  flows=$n"
  else
    echo "[FAIL] $tag rc=$rc flows=$n (log kept: logs/$tag.log)"
  fi
}
export -f run_one; export P SIM LD_LIBRARY_PATH

ls $P/configs/ps5_*.txt | sed "s#.*/##; s#\.txt##" | xargs -P 2 -I{} bash -c "run_one {}"

echo "== batch finished; summarising =="
python3 - <<"PY"
import csv, math, os
P="/work/psweep200"
def metrics(d):
    ft=os.path.join(d,"flow_timing.csv")
    if not os.path.isfile(ft): return None
    inc=[]; last=[]; bg=None
    for x in csv.DictReader(open(ft)):
        fid=int(x["flow_id"])
        fct=int(x["last_ack_ns"])-int(x["first_data_tx_ns"])
        if 1<=fid<=64:
            inc.append(fct); last.append(int(x["last_ack_ns"]))
        elif fid==0:
            bg=fct
    if not inc: return None
    inc.sort()
    q=0; rs=os.path.join(d,"round_summary.csv")
    if os.path.isfile(rs):
        q=max(int(x["selected_link_peak_queue"]) for x in csv.DictReader(open(rs)))
    pe=os.path.join(d,"pfc_events.csv")
    pfc=(open(pe).read().count("\n")-1) if os.path.isfile(pe) else -1
    return ((max(last)-20000000)/1e6, sum(inc)/len(inc)/1e6,
            inc[max(0,math.ceil(0.99*len(inc))-1)]/1e6, q/1e6, pfc,
            (bg/1e6 if bg is not None else float("nan")), len(inc))
rows=[["sweep","value","cell","cct_ms","mean_fct_ms","p99_fct_ms",
       "qpeak_MB","pfc_rows","bg_fct_ms","n_incast"]]
CELLS=(
 [("eta",v,"ps5_eta%s"%v.replace("0.","").ljust(3,"0")) for v in ("0.20","0.35","0.65","0.80")]
+[("eta","0.50","REUSE:fm200g_s5_cbap")]
+[("lease",v,"ps5_lease%04d"%int(v)) for v in ("250","500","2000","4000")]
+[("lease","1000","REUSE:fm200g_s5_cbap")]
+[("bmax",v,"ps5_bmax%s"%v.replace("0.","")) for v in
   ("0.005","0.010","0.040","0.080","0.120","0.160","0.200","0.250","0.300")]
+[("bmax","0.020","REUSE:fm200g_s5_cbap")])
for kind,v,tag in CELLS:
    d = "/work/v2_400g/results/fm200g_s5_cbap" if tag.startswith("REUSE") \
        else P+"/results/"+tag
    m=metrics(d)
    if m: rows.append([kind,v,tag,"%.3f"%m[0],"%.3f"%m[1],"%.3f"%m[2],
                       "%.3f"%m[3],m[4],"%.3f"%m[5],m[6]])
    else: rows.append([kind,v,tag,"MISSING","","","","","",""])
with open(P+"/sweep_summary.csv","w",newline="") as f:
    csv.writer(f).writerows(rows)
for r in rows: print("%-6s %-6s %-24s %s"%(r[0],r[1],r[2]," ".join(str(x) for x in r[3:])))
PY
