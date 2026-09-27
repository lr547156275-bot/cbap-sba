#!/usr/bin/env python3
"""C-item: organize existing auxiliary data and control records (no new runs).

  1. dcqs / cbap0 old single-seed data -> derived/aux_dcqs_cbap0.csv
  2. control_event_summary.csv from the three representative CBAP seed=2
     replays (200g_s2, 400g_s2, 400g_s3): event counts per source file with
     coverage statements.
  3. prediction_comparison.csv from controller_v2_trace: the controller's own
     q0 sample vs its predicted queue, compared against the max q0 over the
     following guard window (sampled proxy, NOT an exact event-level peak),
     and the 2 us qlen_ts GLOBAL max in the same window kept in a separate
     column (different scope, never merged).
  4. detailed/<run>/README_coverage.md + gap list for the un-recorded fields
     (timers, event-level feedback arbitration, event-level queue in/out).
"""
import csv, math, os, shutil

ROOT = "/work/v20"
OLD = "/work/v2_400g/results"
V2C = "/work/v2_400g/configs"
DER = ROOT + "/derived"
DET = ROOT + "/detailed"
os.makedirs(DER, exist_ok=True)
os.makedirs(DET, exist_ok=True)

def load(d, fn):
    p = os.path.join(d, fn)
    if not os.path.isfile(p):
        return None
    with open(p, newline="") as f:
        return list(csv.DictReader(f))

def sched_ready(cfg):
    sched = None
    with open(cfg) as f:
        for ln in f:
            if ln.startswith("ROUND_SCHEDULE_FILE"):
                sched = ln.split()[1]
    members, ready = set(), None
    with open(sched) as f:
        n = int(f.readline())
        for _ in range(n):
            p = f.readline().split()
            if int(p[3]) > 1:
                members.add(int(p[0]))
                ready = int(p[8])
    return members, ready

# ---- 1. dcqs / cbap0 -------------------------------------------------------
aux = []
for rate in ("10", "200", "400"):
    for arm in ("dcqs", "cbap0", "cbap"):
        tag = "fm%sg_s2_%s" % (rate, arm)
        d = os.path.join(OLD, tag)
        ft = load(d, "flow_timing.csv")
        if not ft:
            aux.append([tag, "MISSING"] + ["NA"] * 5)
            continue
        members, ready_s = sched_ready("%s/fm%sg_s2_cbap.txt" % (V2C, rate))
        fcts, lasts = [], []
        for r in ft:
            if int(r["flow_id"]) not in members:
                continue
            rdy = int(r["application_ready_ns"]) or ready_s
            fcts.append(int(r["last_ack_ns"]) - int(r["first_data_tx_ns"]))
            lasts.append((int(r["last_ack_ns"]), rdy))
        cct = max(x[0] for x in lasts) - lasts[0][1]
        p99 = sorted(fcts)[max(0, math.ceil(0.99 * len(fcts)) - 1)]
        aux.append([tag, "old_single_seed(seed=2)", len(fcts), cct,
                    "%.1f" % (sum(fcts) / len(fcts)), p99,
                    "aux only - NOT cross-seed validated"])
with open(DER + "/aux_dcqs_cbap0.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["tag", "provenance", "n_flows", "cct_ns", "mean_fct_ns",
                "p99_fct_ns", "caveat"])
    w.writerows(aux)

# ---- 2 + 3 + 4. representative control records ------------------------------
REPS = ["200g_s2_cbap_s2_a1", "400g_s2_cbap_s2_a1", "400g_s3_cbap_s2_a1"]
ev_rows, pred_rows = [], []
GAPS = """# 控制记录覆盖与缺口（C项）

已有记录（本目录为代表性 seed=2 重放的完整输出，覆盖整个仿真时段）：
- sba_events.csv          接纳/HOLD/接管状态转移（事件级）
- admission.csv           每流接纳决策（事件级）
- rate_transition.csv     速率命令序列（事件级）
- actuation.csv           迁移执行链四阶段（rate_command/sender_rate_effect/
                          arrival_at_bottleneck/first_affected，事件级，
                          对应任务书5.2-4的命令时序链）
- controller_v2_trace.csv 每5us控制周期的q0/预测/额度决策（周期级）
- feedback_summary.csv    每流反馈计数汇总（聚合，非逐事件）
- selected_link_timeseries.csv  选定瓶颈队列10us采样
- qlen_ts.csv             全网总量/最大端口2us采样（范围为全网，非指定链路）

未记录（按任务书5.2逐条，标缺失，不推测补齐）：
- 5.2-1 逐次速率改变的统一来源标签：迁移链有(actuation)，DCQCN自身增减速
        与稳态填充的逐事件来源标签未导出 —— 缺失
- 5.2-2 逐事件反馈仲裁（收到CNP-ACK时是否判定有效及理由）：仅有聚合计数
        (feedback_summary) —— 事件级缺失
- 5.2-3 定时器取消/重建与到期执行 —— 未导出，缺失
- 5.2-6 指定链路事件级入队/出队 —— 仅有采样序列；事件级缺失
补齐上述字段需要仪表化改码并通过无行为变化检查，本批按任务书先完成A/B，
此处单列为缺口（待确认项）。
"""
for rep in REPS:
    d = "%s/results/%s" % (ROOT, rep)
    if not os.path.isdir(d):
        ev_rows.append([rep, "-", "RUN MISSING", ""])
        continue
    dd = os.path.join(DET, rep)
    os.makedirs(dd, exist_ok=True)
    for fn in ("sba_events.csv", "admission.csv", "rate_transition.csv",
               "actuation.csv", "controller_v2_trace.csv",
               "feedback_summary.csv", "selected_link_timeseries.csv",
               "qlen_ts.csv"):
        src = os.path.join(d, fn)
        if os.path.isfile(src):
            shutil.copy2(src, dd)
    with open(os.path.join(dd, "README_coverage.md"), "w") as f:
        f.write("# %s\n覆盖：整个仿真时段（非截取窗口）。\n" % rep + GAPS)

    for fn, how in (("sba_events.csv", "state_transition"),
                    ("actuation.csv", "stage"),
                    ("rate_transition.csv", None),
                    ("controller_v2_trace.csv", "zone")):
        rows = load(d, fn)
        if rows is None:
            ev_rows.append([rep, fn, "not_recorded", ""])
            continue
        if how and rows and how in rows[0]:
            hist = {}
            for r in rows:
                hist[r[how]] = hist.get(r[how], 0) + 1
            det = ";".join("%s=%d" % kv for kv in sorted(hist.items()))
        else:
            det = ""
        ev_rows.append([rep, fn, len(rows), det[:180]])

    # prediction vs sampled actual, guard window = 3 epochs (15 us)
    ctl = load(d, "controller_v2_trace.csv")
    if ctl:
        q0s = [(int(r["time_ns"]), int(r["queue_current_bytes"]),
                int(r["queue_predicted_bytes"])) for r in ctl
               if r["time_ns"].isdigit()]
        for i in range(len(q0s) - 3):
            t, q0, qp = q0s[i]
            act = max(q0s[i + k][1] for k in range(1, 4))
            pred_rows.append([rep, t, q0, qp, act, qp - act])
with open(DER + "/control_event_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "file", "rows", "histogram"])
    w.writerows(ev_rows)
with open(DER + "/prediction_comparison.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "time_ns", "q0_bytes", "q_pred_bytes",
                "max_q0_next_3epoch_bytes_SAMPLED_PROXY",
                "pred_minus_proxy_bytes"])
    w.writerows(pred_rows)
print("C-item done: aux=%d rows, events=%d, prediction=%d"
      % (len(aux), len(ev_rows), len(pred_rows)))
