import csv, math, os

S4 = "/work/s4match"

def ms(d, lo=1, hi=64):
    ft = d + "/flow_timing.csv"
    if not os.path.isfile(ft):
        return None
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
    rs = d + "/round_summary.csv"
    if os.path.isfile(rs):
        qs = [int(r["selected_link_peak_queue"]) for r in csv.DictReader(open(rs))
              if r.get("selected_link_peak_queue", "").strip()]
        q = max(qs) if qs else 0
    pe = d + "/pfc_events.csv"
    pfc = (open(pe).read().count("\n") - 1) if os.path.isfile(pe) else -1
    return ((max(last) - 20000000) / 1e6, sum(inc)/len(inc)/1e6,
            inc[max(0, math.ceil(0.99*len(inc))-1)]/1e6, q/1e6, pfc, len(inc))

CELLS = [
    ("cbap_matched", "m_s4match_cbap", "2000Mb/s", "4000Mb/s",
     "CBAP with the DCQCN baseline's speed-normalised backend"),
    ("cbap_legacy", "m_s4match_cbap_lai", "50Mb/s", "100Mb/s",
     "CBAP with the historical backend values (all prior campaigns)"),
    ("dcqn_baseline", "m_s4match_dcqn", "2000Mb/s", "4000Mb/s",
     "DCQCN baseline reference"),
]
rows = [["variant", "cell", "rate_ai", "rate_hai", "note", "n_incast",
         "cct_ms", "mean_fct_ms", "p99_fct_ms", "qpeak_MB", "pfc_rows",
         "cct_delta_vs_legacy_pct"]]
base = ms(S4 + "/results/m_s4match_cbap_lai")
for variant, cell, ai, hai, note in CELLS:
    m = ms(S4 + "/results/" + cell)
    delta = ""
    if m and base and variant == "cbap_matched":
        delta = "%+.2f" % ((m[0] - base[0]) / base[0] * 100.0)
    if m:
        rows.append([variant, cell, ai, hai, note, m[5], "%.3f" % m[0],
                     "%.3f" % m[1], "%.3f" % m[2], "%.3f" % m[3], m[4], delta])
    else:
        rows.append([variant, cell, ai, hai, note, "MISSING"] + [""]*6)
with open(S4 + "/s4_backend_match.csv", "w", newline="") as f:
    csv.writer(f).writerows(rows)
for r in rows:
    print("  " + "  ".join(str(x).ljust(14) for x in r))
