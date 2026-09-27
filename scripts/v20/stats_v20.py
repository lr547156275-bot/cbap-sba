#!/usr/bin/env python3
"""V20 batch-1 statistics: per-flow, per-run, per-seed comparisons, cross-seed
summaries, background common windows, and file coverage.

Metric definitions (task book section 7):
  batch members   from the schedule file (participant_count > 1), NOT src!=65
  per-flow FCT    last_ack_ns - first_data_tx_ns          (completed sync flows)
  ready-to-done   last_ack_ns - application_ready_ns      (kept separately)
  batch CCT       max(member last_ack_ns) - common application_ready_ns;
                  ready from the flow_timing column when > 0, else from the
                  schedule (source recorded).  Valid only if ALL members done.
  p99             nearest-rank: sorted[ceil(0.99*N)-1]  (== max at N=32/64)
  queue           three fields kept apart: sampled peak of the selected link
                  timeseries, per-round selected_link_peak max, qlen_ts global
                  max.  Never mixed.
  background      common-window progress on flow 0 snd_una (20 us samples):
                  start = first common sample >= batch ready; end = first
                  common sample >= max completion across the comparison set.
Data sources: seed==2 A-cells use the OLD formal directories (reuse audited);
everything else uses /work/v20/results/<run_id>.
"""
import csv, math, os

ROOT = "/work/v20"
OLD = "/work/v2_400g/results"
V2C = "/work/v2_400g/configs"
DER = ROOT + "/derived"
os.makedirs(DER, exist_ok=True)

PREF = {"200g_s2": "fm200g_s2", "400g_s2": "fm400g_s2",
        "400g_s3": "fm400g_s3", "400g_s5": "fm400g_s5"}
ALGS = ["cbap", "hpcc", "dcqn", "dctcp", "timely"]

# ---------------------------------------------------------------- helpers ---
def read_plan():
    with open(ROOT + "/plan/run_plan.csv", newline="") as f:
        return list(csv.DictReader(f))

def src_dir(u):
    if u["group"] == "A" and u["seed"] == "2":
        return "%s/%s_%s" % (OLD, PREF[u["case"]], u["alg"])
    return "%s/results/%s" % (ROOT, u["run_id"])

def load_csv(d, fn):
    p = os.path.join(d, fn)
    if not os.path.isfile(p):
        return None
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

def schedule_of(case):
    """returns (member_ids, common_ready_ns, bg_ids)"""
    cfg = "%s/%s_cbap.txt" % (V2C, PREF[case])
    sched = None
    with open(cfg) as f:
        for ln in f:
            if ln.startswith("ROUND_SCHEDULE_FILE"):
                sched = ln.split()[1]
    members, ready, bg = set(), None, set()
    with open(sched) as f:
        n = int(f.readline())
        for _ in range(n):
            p = f.readline().split()
            fid, part, rdy = int(p[0]), int(p[3]), int(p[8])
            if part > 1:
                members.add(fid)
                ready = rdy
            else:
                bg.add(fid)
    return members, ready, bg

def nearest_rank(vals, q):
    v = sorted(vals)
    return v[max(0, math.ceil(q * len(v)) - 1)]

def col(hdr_row, *cands):
    for c in cands:
        if c in hdr_row:
            return c
    return None

SCHED = {c: schedule_of(c) for c in PREF}

# ---------------------------------------------------- per-flow / per-run ----
units = read_plan()
pf_rows, pr_rows, cov_rows = [], [], []
RUN = {}          # run_id -> per-run dict for later stages

EXPECT_FILES = ["flow_timing.csv", "flow_summary.csv", "round_summary.csv",
                "group_round_summary.csv", "selected_flow_timeseries.csv",
                "selected_link_timeseries.csv", "pfc_events.csv",
                "qlen_ts.csv", "feedback_summary.csv", "admission.csv",
                "sba_events.csv", "rate_transition.csv", "actuation.csv",
                "controller_v2_trace.csv", "port_summary.csv"]
CBAP_ONLY = {"admission.csv", "sba_events.csv", "rate_transition.csv",
             "actuation.csv", "controller_v2_trace.csv", "port_summary.csv",
             "feedback_summary.csv"}

for u in units:
    d = src_dir(u)
    run_id = u["run_id"]
    members, ready_sched, _bg = SCHED[u["case"]]
    ft = load_csv(d, "flow_timing.csv")
    status = "missing_dir"
    if os.path.isdir(d):
        stp = os.path.join(d, "STATUS")
        status = open(stp).read().split()[0] if os.path.isfile(stp) else \
            ("old_formal" if d.startswith(OLD) else "no_status")

    # ---- file coverage
    for fn in EXPECT_FILES:
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                data = fh.read()
            nrows = data.count(b"\n") - 1
            cov_rows.append([run_id, fn, nrows, len(data), "present"])
        else:
            why = ("not_applicable_baseline" if fn in CBAP_ONLY and
                   u["alg"] != "cbap" else "not_recorded")
            cov_rows.append([run_id, fn, 0, 0, why])

    if not ft:
        pr_rows.append([run_id, u["group"], u["case"], u["alg"], u["variant"],
                        u["seed"], u["typ"], status, len(members)] +
                       ["NA"] * 13 + ["flow_timing missing"])
        continue

    seed_col = set(r["seed"] for r in ft)
    fcts, ready_common, done, missing = [], None, 0, []
    src_ready = "column"
    for r in ft:
        fid = int(r["flow_id"])
        if fid not in members:
            continue
        rdy = int(r["application_ready_ns"])
        if rdy <= 0:
            rdy = ready_sched
            src_ready = "schedule"
        if ready_common is None:
            ready_common = rdy
        tot, ack = int(r["total_size_bytes"]), int(r["acked_bytes"])
        last, ftx = int(r["last_ack_ns"]), int(r["first_data_tx_ns"])
        complete = (ack >= tot and last > 0)
        if complete:
            done += 1
            fcts.append((fid, last - ftx, last - rdy, last))
        else:
            missing.append(fid)
        pf_rows.append([run_id, 1, fid, r["src"], r["dst"], "sync", tot, ack,
                        int(complete), rdy, src_ready, ftx, last,
                        (last - ftx) if complete else "NA",
                        (last - rdy) if complete else "NA"])

    n_exp = len(members)
    if done == n_exp:
        cct = max(x[3] for x in fcts) - ready_common
        mean_f = sum(x[1] for x in fcts) / done
        p99_f = nearest_rank([x[1] for x in fcts], 0.99)
        note = ""
    else:
        cct = mean_f = p99_f = "NA"
        note = "incomplete: missing flows %s" % missing[:8]

    # queue metrics, kept separate
    def peak_of(fn, *cands):
        rows = load_csv(d, fn)
        if not rows:
            return "NA"
        c = col(rows[0], *cands)
        if not c:
            return "NA"
        try:
            return max(int(float(r[c])) for r in rows)
        except ValueError:
            return "NA"
    q_sel = peak_of("selected_link_timeseries.csv",
                    "queue_bytes", "qlen_bytes", "queue")
    q_round = peak_of("round_summary.csv", "selected_link_peak_queue")
    q_glob = peak_of("qlen_ts.csv", "max_port_queue_bytes")
    rs = load_csv(d, "round_summary.csv")
    cnp = sum(int(r["cnp_count"]) for r in rs) if rs else "NA"
    gr = load_csv(d, "group_round_summary.csv")
    ecn = sum(int(r["group_ecn_marks"]) for r in gr) if gr else "NA"
    pf = load_csv(d, "pfc_events.csv")
    pfc = len(pf) if pf is not None else "NA"

    pr_rows.append([run_id, u["group"], u["case"], u["alg"], u["variant"],
                    u["seed"], u["typ"], status, n_exp, done, cct, mean_f,
                    p99_f, q_sel, q_round, q_glob, cnp, ecn, pfc,
                    ";".join(sorted(seed_col)), src_ready,
                    os.path.relpath(d, "/work"), note])
    RUN[run_id] = dict(u=u, dir=d, cct=cct, p99=p99_f, mean=mean_f,
                       done=done, n_exp=n_exp, ready=ready_common)

with open(DER + "/per_flow_metrics.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "batch_id", "flow_id", "src", "dst", "role",
                "total_bytes", "acked_bytes", "complete", "ready_ns",
                "ready_source", "first_data_tx_ns", "last_ack_ns", "fct_ns",
                "ready_to_done_ns"])
    w.writerows(pf_rows)
with open(DER + "/per_run_metrics.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "group", "case", "alg", "variant", "seed", "type",
                "status", "expected_flows", "completed_flows", "cct_ns",
                "mean_fct_ns", "p99_fct_ns", "qpeak_selected_ts_bytes",
                "qpeak_round_selected_bytes", "qpeak_qlents_global_bytes",
                "cnp_count_sum", "ecn_marks_sum", "pfc_event_rows",
                "seed_col_in_csv", "ready_source", "src_dir", "note"])
    w.writerows(pr_rows)
with open(DER + "/../plan/file_coverage.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "file", "rows", "bytes", "state"])
    w.writerows(cov_rows)

# ------------------------------------------------- background windows -------
def bg_series(d):
    rows = load_csv(d, "selected_flow_timeseries.csv")
    if not rows:
        return None
    out = {}
    for r in rows:
        if r["flow_id"] == "0":
            t = int(round(float(r["time"]) * 1e9))
            out[t] = int(r["snd_una"])
    return out

def find_id(case, alg, variant, seed):
    if variant == "full":
        return "%s_%s_s%d_a1" % (case, alg, seed)
    return "%s_cbap_%s_s%d_a1" % (case, variant, seed)

bg_rows, cmp_rows = [], []
def window_for(set_id, case, seed, entries):
    """entries: list of (label, run_id).  Emits background_windows rows."""
    ready = SCHED[case][1]
    series, endreq = {}, 0
    ok = True
    for lab, rid in entries:
        if rid not in RUN or RUN[rid]["cct"] == "NA":
            ok = False
            continue
        s = bg_series(RUN[rid]["dir"])
        if not s:
            ok = False
            continue
        series[rid] = s
        endreq = max(endreq, RUN[rid]["ready"] + RUN[rid]["cct"])
    if not ok or len(series) != len(entries):
        for lab, rid in entries:
            bg_rows.append([case, seed, set_id, rid, 0, ready, endreq] +
                           ["NA"] * 5 + ["set incomplete or series missing"])
        return
    common = set.intersection(*[set(s.keys()) for s in series.values()])
    starts = sorted(t for t in common if t >= ready)
    ends = sorted(t for t in common if t >= endreq)
    if not starts or not ends:
        for lab, rid in entries:
            bg_rows.append([case, seed, set_id, rid, 0, ready, endreq] +
                           ["NA"] * 5 + ["no common sample covers window"])
        return
    t0, t1 = starts[0], ends[0]
    for lab, rid in entries:
        s = series[rid]
        d_bytes = s[t1] - s[t0]
        gbps = d_bytes * 8.0 / (t1 - t0)
        bg_rows.append([case, seed, set_id, rid, 0, t0, t1, s[t0], s[t1],
                        d_bytes, t1 - t0, "%.4f" % gbps, "ok"])

for case in PREF:
    for seed in range(1, 6):
        window_for("A5_%s_s%d" % (case, seed), case, seed,
                   [(a, find_id(case, a, "full", seed)) for a in ALGS])
for case in ("200g_s2", "400g_s2"):
    for seed in range(1, 6):
        window_for("B3_%s_s%d" % (case, seed), case, seed,
                   [("full", find_id(case, "cbap", "full", seed)),
                    ("no_migration", find_id(case, "cbap", "no_migration", seed)),
                    ("no_phase_spread",
                     find_id(case, "cbap", "no_phase_spread", seed))])

with open(DER + "/background_windows.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "seed", "comparison_set_id", "run_id", "bg_flow_id",
                "win_start_ns", "win_end_ns", "snd_una_start", "snd_una_end",
                "delta_bytes", "win_len_ns", "avg_gbps", "validity"])
    w.writerows(bg_rows)

# --------------------------------------------- per-seed comparisons ---------
for case in PREF:
    for seed in range(1, 6):
        ids = {a: find_id(case, a, "full", seed) for a in ALGS}
        vals = {a: RUN.get(ids[a]) for a in ALGS}
        for met in ("cct", "p99"):
            c = vals["cbap"]
            if not c or c[met] == "NA":
                continue
            base_vals = {a: vals[a][met] for a in ALGS[1:]
                         if vals[a] and vals[a][met] != "NA"}
            for a, bv in base_vals.items():
                cmp_rows.append([case, seed, "A5_%s_s%d" % (case, seed), met,
                                 "cbap_vs_" + a, ids["cbap"], c[met], ids[a],
                                 bv, bv - c[met],
                                 "%.4f" % (100.0 * (bv - c[met]) / bv), ""])
            if base_vals:
                fa = min(base_vals, key=lambda a: base_vals[a])
                bv = base_vals[fa]
                cmp_rows.append([case, seed, "A5_%s_s%d" % (case, seed), met,
                                 "cbap_vs_fastest(" + fa + ")", ids["cbap"],
                                 c[met], ids[fa], bv, bv - c[met],
                                 "%.4f" % (100.0 * (bv - c[met]) / bv), ""])
for case in ("200g_s2", "400g_s2"):
    for seed in range(1, 6):
        full = RUN.get(find_id(case, "cbap", "full", seed))
        for var in ("no_migration", "no_phase_spread"):
            v = RUN.get(find_id(case, "cbap", var, seed))
            for met in ("cct", "p99", "mean"):
                if not full or not v or full[met] == "NA" or v[met] == "NA":
                    continue
                cmp_rows.append([case, seed, "B3_%s_s%d" % (case, seed), met,
                                 "%s_minus_full" % var,
                                 find_id(case, "cbap", "full", seed),
                                 full[met],
                                 find_id(case, "cbap", var, seed), v[met],
                                 v[met] - full[met],
                                 "%.4f" % (100.0 * (v[met] - full[met]) /
                                           full[met]), ""])
with open(DER + "/comparisons_per_seed.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "seed", "comparison_set_id", "metric", "pair",
                "run_id_1", "value_1_ns", "run_id_2", "value_2_ns",
                "delta_ns", "pct", "invalid_reason"])
    w.writerows(cmp_rows)

# --------------------------------------------- cross-seed summaries ---------
def agg(vals):
    v = [x for x in vals if x != "NA"]
    if not v:
        return ["0", "NA", "NA", "NA", "NA"]
    n = len(v)
    m = sum(v) / n
    sd = (sum((x - m) ** 2 for x in v) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return [str(n), "%.1f" % m, "%.1f" % sd, str(min(v)), str(max(v))]

sum_rows = []
combos = sorted(set((u["case"], u["alg"], u["variant"]) for u in units))
for case, alg, var in combos:
    ids = [find_id(case, alg, var, s) for s in range(1, 6)]
    got = [RUN[i] for i in ids if i in RUN]
    for met, name in (("cct", "cct_ns"), ("mean", "mean_fct_ns"),
                      ("p99", "p99_fct_ns")):
        sum_rows.append([case, alg, var, name] +
                        agg([g[met] for g in got]))
with open(DER + "/summary_across_seeds.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "alg", "variant", "metric", "n", "mean", "std",
                "min", "max"])
    w.writerows(sum_rows)

print("stats done: per_flow=%d rows, per_run=%d, comparisons=%d, bg=%d, "
      "summary=%d" % (len(pf_rows), len(pr_rows), len(cmp_rows), len(bg_rows),
                      len(sum_rows)))
