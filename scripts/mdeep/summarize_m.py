#!/usr/bin/env python3
"""M campaign summary: per cell -> overall CCT, mean/p99 FCT, per-side CCT,
selected-link peak queue, per-node qlen peaks (81-84), PFC, per-bg acked."""
import csv, math, os

M = "/work/mdeep"
INC = {"m1": (2, 61), "m2": (2, 61), "m3": (2, 61), "m4": (4, 55)}
NBG = {"m1": 2, "m2": 2, "m3": 2, "m4": 4}

def metrics(sc, d):
    lo, hi = INC[sc]
    ft = os.path.join(d, "flow_timing.csv")
    if not os.path.isfile(ft):
        return None
    inc, last, side = [], [], {}
    for x in csv.DictReader(open(ft)):
        fid = int(x["flow_id"])
        if lo <= fid <= hi:
            inc.append(int(x["last_ack_ns"]) - int(x["first_data_tx_ns"]))
            last.append(int(x["last_ack_ns"]))
            side.setdefault(x["dst"], []).append(int(x["last_ack_ns"]))
    if not inc:
        return None
    inc.sort()
    q = max(int(r["selected_link_peak_queue"])
            for r in csv.DictReader(open(d + "/round_summary.csv")))
    pfc = open(d + "/pfc_events.csv").read().count("\n") - 1
    bg = {}
    fs = d + "/flow_summary.csv"
    if os.path.isfile(fs):
        for r in csv.DictReader(open(fs)):
            if int(r["flow_id"]) < NBG[sc]:
                bg["bg%s" % r["flow_id"]] = int(r["acked_bytes"]) / 1e6
    qn = {}
    ql = d + "/qlen.txt"
    if os.path.isfile(ql):
        for ln in open(ql):
            w = ln.split()
            if len(w) == 3 and w[1] == "1":
                try:
                    node, qb = int(w[0]), int(w[2])
                except ValueError:
                    continue
                if node in (81, 82, 83, 84):
                    qn[node] = max(qn.get(node, 0), qb)
    return ((max(last) - 20000000) / 1e6, sum(inc) / len(inc) / 1e6,
            inc[max(0, math.ceil(0.99 * len(inc)) - 1)] / 1e6,
            {k: (max(v) - 20000000) / 1e6 for k, v in sorted(side.items())},
            q / 1e6, pfc, bg, {k: v / 1e6 for k, v in sorted(qn.items())})

rows = [["scen", "alg", "cct_ms", "mean_fct_ms", "p99_fct_ms",
         "side_cct_ms", "qpeak_sel_MB", "pfc_rows", "bg_acked_MB",
         "qlen_node_peaks_MB", "n_incast"]]
for sc in ("m1", "m2", "m3", "m4"):
    for alg in ("cbap", "hpcc", "dcqn", "dctcp", "timely", "dart"):
        cell = "%s_400g_%s" % (sc, alg)
        m = metrics(sc, M + "/results/" + cell)
        if m:
            lo, hi = INC[sc]
            rows.append([sc, alg, "%.3f" % m[0], "%.3f" % m[1],
                         "%.3f" % m[2],
                         ";".join("%s:%.3f" % kv for kv in m[3].items()),
                         "%.3f" % m[4], m[5],
                         ";".join("%s:%.1f" % kv for kv in m[6].items()),
                         ";".join("%s:%.3f" % kv for kv in m[7].items()),
                         hi - lo + 1])
        else:
            rows.append([sc, alg, "MISSING"] + [""] * 8)
with open(M + "/m_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
for r in rows:
    print("%-4s %-7s %s" % (r[0], r[1], "  ".join(str(x) for x in r[2:])))
