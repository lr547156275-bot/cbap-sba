import csv, math, os
S6 = "/work/s6dual"
def metrics(d):
    ft = os.path.join(d, "flow_timing.csv")
    if not os.path.isfile(ft): return None
    inc, last = [], []
    for x in csv.DictReader(open(ft)):
        fid = int(x["flow_id"])
        if 2 <= fid <= 61:
            inc.append(int(x["last_ack_ns"]) - int(x["first_data_tx_ns"]))
            last.append(int(x["last_ack_ns"]))
    if not inc: return None
    inc.sort()
    q = 0
    rs = os.path.join(d, "round_summary.csv")
    if os.path.isfile(rs):
        q = max(int(r["selected_link_peak_queue"]) for r in csv.DictReader(open(rs)))
    pe = os.path.join(d, "pfc_events.csv")
    pfc = (open(pe).read().count("\n") - 1) if os.path.isfile(pe) else -1
    # background progress from flow_summary (flows 0,1 = the two bg flows)
    bg = []
    fs = os.path.join(d, "flow_summary.csv")
    if os.path.isfile(fs):
        for r in csv.DictReader(open(fs)):
            if int(r["flow_id"]) in (0, 1):
                bg.append(int(r["acked_bytes"]))
    # both-bottleneck queue peaks from qlen.txt (space-separated: time node if qbytes...)
    q83 = q84 = 0
    ql = os.path.join(d, "qlen.txt")
    if os.path.isfile(ql):
        for ln in open(ql):
            w = ln.split()
            if len(w) == 3 and w[1] == "1":      # bottleneck port = if 1
                try: node, qb = int(w[0]), int(w[2])
                except ValueError: continue
                if node == 83: q83 = max(q83, qb)
                elif node == 84: q84 = max(q84, qb)
    return ((max(last) - 20000000) / 1e6, sum(inc)/len(inc)/1e6,
            inc[max(0, math.ceil(0.99*len(inc))-1)]/1e6, q/1e6, pfc,
            sum(bg)/1e6 if bg else float("nan"), q84/1e6, q83/1e6, len(inc))
rows = [["case","alg","cct_ms","mean_fct_ms","p99_fct_ms","qpeak_sel_MB",
         "pfc_rows","bg_acked_MB","q84_MB","q83_MB","n_incast"]]
for rate in ("200","400"):
    for alg in ("cbap","hpcc","dcqn","dctcp","timely","dart","dartv1","dartv2"):
        cell = "fm%sg_s6_%s" % (rate, alg)
        m = metrics(S6 + "/results/" + cell)
        if m: rows.append(["%sg_s6"%rate, alg] + ["%.3f"%m[0],"%.3f"%m[1],"%.3f"%m[2],
                          "%.3f"%m[3], m[4], "%.1f"%m[5], "%.3f"%m[6], "%.3f"%m[7], m[8]])
        else: rows.append(["%sg_s6"%rate, alg, "MISSING"] + [""]*8)
with open(S6 + "/s6_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
for r in rows: print("%-9s %-8s %s" % (r[0], r[1], " ".join(str(x) for x in r[2:])))
