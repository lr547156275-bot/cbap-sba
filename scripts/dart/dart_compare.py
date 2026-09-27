#!/usr/bin/env python3
"""DART-RA vs the old seed=2 formal matrix (S1-S5 x 10/200/400G).
Metrics per V20 definitions: CCT from schedule ready (20ms), per-flow FCT
last_ack-first_tx, nearest-rank p99, selected-link peak queue, PFC rows."""
import csv, math, os
OLD = "/work/v2_400g/results"
D = "/work/dart/results"
ALGS = ["dart", "cbap", "dcqn", "dctcp", "timely", "hpcc"]
out = [["case", "alg", "cct_ms", "mean_fct_ms", "p99_fct_ms",
        "qpeak_selected_bytes", "pfc_rows", "source"]]
def stats(d, want):
    p = os.path.join(d, "flow_timing.csv")
    if not os.path.isfile(p):
        return None
    rows = list(csv.DictReader(open(p, newline="")))
    f = [(int(r["last_ack_ns"]) - int(r["first_data_tx_ns"]))
         for r in rows if 1 <= int(r["flow_id"]) <= want]
    last = [int(r["last_ack_ns"]) for r in rows if 1 <= int(r["flow_id"]) <= want]
    if len(f) != want:
        return ("INCOMPLETE %d/%d" % (len(f), want),)
    f.sort()
    rs = list(csv.DictReader(open(os.path.join(d, "round_summary.csv"), newline="")))
    q = max(int(r["selected_link_peak_queue"]) for r in rs)
    pfc = open(os.path.join(d, "pfc_events.csv")).read().count("\n") - 1
    return ((max(last) - 20000000) / 1e6, sum(f) / len(f) / 1e6,
            f[max(0, math.ceil(0.99 * len(f)) - 1)] / 1e6, q, pfc)
for rate in ("10", "200", "400"):
    for s in ("s1", "s2", "s3", "s4", "s5"):
        want = 32 if s == "s5" else 64
        case = "%sg_%s" % (rate, s)
        for alg in ALGS:
            if alg == "dart":
                d, src = "%s/dart_%sg_%s" % (D, rate, s), "new(dart-ra)"
            else:
                d, src = "%s/fm%sg_%s_%s" % (OLD, rate, s, alg), "old seed2"
            st = stats(d, want)
            if st is None:
                out.append([case, alg, "MISSING", "", "", "", "", src])
            elif len(st) == 1:
                out.append([case, alg, st[0], "", "", "", "", src])
            else:
                out.append([case, alg, "%.3f" % st[0], "%.3f" % st[1],
                            "%.3f" % st[2], st[3], st[4], src])
with open("/work/dart/dart_comparison.csv", "w", newline="") as fo:
    csv.writer(fo).writerows(out)
print("%-10s %-7s %10s %10s %10s %14s %6s" % ("case", "alg", "cct_ms", "meanFCT", "p99FCT", "qpeak_B", "pfc"))
for r in out[1:]:
    if r[1] in ("dart", "cbap", "dcqn"):
        print("%-10s %-7s %10s %10s %10s %14s %6s" % tuple(r[:7]))
print("full table: /work/dart/dart_comparison.csv")
