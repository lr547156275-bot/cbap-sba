import csv, math, os

X = "/work/ext"
ALGS = ("cbap", "hpcc", "dcqn", "dctcp", "timely", "dart")
RANGE = {"e1": (1, 10**9), "e2": (1, 10**9), "e3": (2, 10**9)}

def metrics(scen, d):
    ft = os.path.join(d, "flow_timing.csv")
    if not os.path.isfile(ft):
        return None
    lo, hi = RANGE[scen]
    inc, last, per = [], [], {}
    for x in csv.DictReader(open(ft)):
        fid = int(x["flow_id"])
        if lo <= fid <= hi:
            f = int(x["last_ack_ns"]) - int(x["first_data_tx_ns"])
            inc.append(f); last.append(int(x["last_ack_ns"]))
            per.setdefault(x["dst"], []).append(f)
    if not inc:
        return None
    inc.sort()
    q = 0
    rs = os.path.join(d, "round_summary.csv")
    if os.path.isfile(rs):
        qs = [int(r["selected_link_peak_queue"]) for r in csv.DictReader(open(rs))
              if r.get("selected_link_peak_queue", "").strip()]
        q = max(qs) if qs else 0
    pe = os.path.join(d, "pfc_events.csv")
    pfc = (open(pe).read().count("\n") - 1) if os.path.isfile(pe) else -1
    return ((max(last) - 20000000) / 1e6, sum(inc)/len(inc)/1e6,
            inc[max(0, math.ceil(0.99*len(inc))-1)]/1e6, q/1e6, pfc,
            {k: sum(v)/len(v)/1e6 for k, v in sorted(per.items())}, len(inc))

rows = [["scen", "alg", "n_incast", "cct_ms", "mean_fct_ms", "p99_fct_ms",
         "qpeak_MB", "pfc_rows", "per_dst_mean_fct_ms", "cbap_backend"]]
for scen in ("e1", "e2"):
    for alg in ALGS:
        cell = "%s_400g_%s" % (scen, alg)
        d = "%s/results/%s" % (X, cell)
        m = metrics(scen, d)
        note = ""
        if alg == "cbap":
            # read the ACTUAL values this cell ran with
            cfg = open("%s/configs/%s.txt" % (X, cell)).read()
            ai = [l.split(None, 1)[1] for l in cfg.splitlines()
                  if l.startswith("RATE_AI ")][:1]
            hai = [l.split(None, 1)[1] for l in cfg.splitlines()
                   if l.startswith("RATE_HAI ")][:1]
            note = "RATE_AI %s / RATE_HAI %s (legacy, as in all prior campaigns)" % (
                ai[0] if ai else "?", hai[0] if hai else "?")
        if m:
            rows.append([scen, alg, m[6], "%.3f" % m[0], "%.3f" % m[1],
                         "%.3f" % m[2], "%.3f" % m[3], m[4],
                         ";".join("%s:%.2f" % kv for kv in m[5].items()), note])
        else:
            rows.append([scen, alg, "MISSING"] + [""]*7)
with open(X + "/ext_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
print("%-4s %-7s %6s %9s %9s %9s %9s %6s  %s" % (
    "scen", "alg", "n", "cct", "meanFCT", "p99FCT", "qpeakMB", "pfc", "per-dst"))
for r in rows[1:]:
    print("%-4s %-7s %6s %9s %9s %9s %9s %6s  %s" % tuple(r[:9]))
