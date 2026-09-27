#!/usr/bin/env python3
"""Semantic gate for the two B-group ablations (seed=2 cells).

Evidence (v2, after empirical calibration against the real outputs):
  no_migration    -> actuation.csv contains NO execution-chain rows
                     (rate_command / sender_rate_effect / arrival_at_bottleneck
                     / first_affected_at_bottleneck).  Trailer counter rows
                     ("counters_*") are bookkeeping, not commands, and are
                     excluded.  Periodic controller still runs and DCQCN
                     feedback still arrives.
  no_phase_spread -> the ACTIVE first-packet spread is off: the batch's
                     first_data_tx_ns collapses to a single instant
                     (span == 0), whereas the full config staggers 64 distinct
                     instants over ~1.4 us.  flow_plan.phase_offset_ns is NOT
                     usable (written at plan time, before the spread applies)
                     - checked empirically and documented.
Writes /work/v20/validation/bvariant_semantics.csv; exit 1 on failure.
"""
import csv, os, sys

ROOT = "/work/v20"
OLDC = "/work/v2_400g/results"
PREF = {"200g_s2": "fm200g_s2", "400g_s2": "fm400g_s2"}
CHAIN = {"rate_command", "sender_rate_effect", "arrival_at_bottleneck",
         "first_affected_at_bottleneck"}

def rows_of(d, fn):
    p = os.path.join(d, fn)
    if not os.path.isfile(p):
        return None
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

def chain_rows(d):
    r = rows_of(d, "actuation.csv")
    if r is None:
        return -1
    return sum(1 for x in r if x.get("stage", "") in CHAIN)

def n_rows(d, fn):
    r = rows_of(d, fn)
    return -1 if r is None else len(r)

def first_tx_span(d):
    r = rows_of(d, "flow_timing.csv")
    if not r:
        return (-1, -1)
    ts = [int(x["first_data_tx_ns"]) for x in r
          if 1 <= int(x["flow_id"]) <= 64]
    return (len(set(ts)), max(ts) - min(ts))

out, fails = [], []
for case in ("200g_s2", "400g_s2"):
    full = "%s/%s_cbap" % (OLDC, PREF[case])
    f_chain = chain_rows(full)
    f_ctl = n_rows(full, "controller_v2_trace.csv")
    f_dist, f_span = first_tx_span(full)

    for var in ("no_migration", "no_phase_spread"):
        d = "%s/results/%s_cbap_%s_s2_a1" % (ROOT, case, var)
        if not os.path.isdir(d):
            fails.append("%s/%s: run dir missing" % (case, var))
            continue
        v_chain = chain_rows(d)
        ctl = n_rows(d, "controller_v2_trace.csv")
        dist, span = first_tx_span(d)
        fb = rows_of(d, "round_summary.csv")
        cnp = sum(int(r["cnp_count"]) for r in fb) if fb else -1

        checks = []
        if var == "no_migration":
            checks.append(("migration_silent", v_chain == 0,
                           "chain rows=%d (full=%d; counter trailer rows "
                           "excluded)" % (v_chain, f_chain)))
            checks.append(("spread_intact", span > 0 and dist > 1,
                           "first_tx distinct=%d span=%dns (full=%d/%dns)"
                           % (dist, span, f_dist, f_span)))
            checks.append(("periodic_alive", ctl > 0.5 * f_ctl,
                           "ctl_trace rows=%d (full=%d)" % (ctl, f_ctl)))
            checks.append(("feedback_alive", cnp > 0,
                           "sum cnp_count=%d" % cnp))
        else:
            checks.append(("spread_off", span == 0 and dist == 1,
                           "first_tx distinct=%d span=%dns (full=%d/%dns)"
                           % (dist, span, f_dist, f_span)))
            checks.append(("migration_alive", v_chain > 0,
                           "chain rows=%d (full=%d)" % (v_chain, f_chain)))
            checks.append(("periodic_alive", ctl > 0.5 * f_ctl,
                           "ctl_trace rows=%d (full=%d)" % (ctl, f_ctl)))
        for name, okv, detail in checks:
            out.append([case, var, name, "PASS" if okv else "FAIL", detail])
            if not okv:
                fails.append("%s/%s %s: %s" % (case, var, name, detail))

os.makedirs(ROOT + "/validation", exist_ok=True)
with open(ROOT + "/validation/bvariant_semantics.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "variant", "check", "verdict", "detail"])
    w.writerows(out)
for r in out:
    print("%-8s %-16s %-18s %-5s %s" % tuple(r))
if fails:
    print("GATE: FAIL")
    sys.exit(1)
print("GATE: PASS -- semantics confirmed, continue remaining seeds")
