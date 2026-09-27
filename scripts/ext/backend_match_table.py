#!/usr/bin/env python3
"""Backend-matching comparison: matched CBAP (RATE_AI 2000/HAI 4000) vs the
legacy control (50/100) in each E scenario, plus the same-scenario dcqn
baseline for reference."""
import csv, math, os

X = "/work/ext"
RANGE = {"e1": (1, 10**9), "e2": (1, 10**9), "e3": (2, 10**9)}

def metrics(scen, d):
    ft = os.path.join(d, "flow_timing.csv")
    if not os.path.isfile(ft):
        return None
    lo, hi = RANGE[scen]
    inc, last = [], []
    for x in csv.DictReader(open(ft)):
        fid = int(x["flow_id"])
        if lo <= fid <= hi:
            inc.append(int(x["last_ack_ns"]) - int(x["first_data_tx_ns"]))
            last.append(int(x["last_ack_ns"]))
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
            inc[max(0, math.ceil(0.99*len(inc))-1)]/1e6, q/1e6, pfc, len(inc))

rows = [["scen", "variant", "rate_ai", "rate_hai", "n_incast",
         "cct_ms", "mean_fct_ms", "p99_fct_ms", "qpeak_MB", "pfc_rows",
         "cct_delta_vs_legacy_pct"]]
for scen in ("e1", "e2"):
    base = metrics(scen, "%s/results/%s_400g_cbap_lai" % (X, scen))
    m = metrics(scen, "%s/results/%s_400g_cbap" % (X, scen))
    d = metrics(scen, "%s/results/%s_400g_dcqn" % (X, scen))
    def row(v, ai, hai, mm, delta=""):
        if not mm:
            return [scen, v, ai, hai, "MISSING"] + [""]*6
        return [scen, v, ai, hai, mm[5], "%.3f" % mm[0], "%.3f" % mm[1],
                "%.3f" % mm[2], "%.3f" % mm[3], mm[4], delta]
    dlt = ""
    if base and m:
        dlt = "%+.2f" % ((m[0] - base[0]) / base[0] * 100.0)
    rows.append(row("cbap_matched", "2000Mb/s", "4000Mb/s", m, dlt))
    rows.append(row("cbap_legacy", "50Mb/s", "100Mb/s", base, "(reference)"))
    rows.append(row("dcqn_baseline", "2000Mb/s", "4000Mb/s", d, ""))
with open(X + "/backend_match.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
for r in rows:
    print("  " + "  ".join(str(x).ljust(13) for x in r))
