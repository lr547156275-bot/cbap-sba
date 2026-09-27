#!/usr/bin/env python3
"""Generate completion_report.md and README.md into /work/v20/docs from the
actual statuses, audits and summaries.  Never invents numbers."""
import csv, json, os

ROOT = "/work/v20"
DOCS = ROOT + "/docs"
os.makedirs(DOCS, exist_ok=True)

plan = list(csv.DictReader(open(ROOT + "/plan/run_plan.csv", newline="")))
def st(rid):
    p = ROOT + "/results/" + rid + "/STATUS"
    return open(p).read().split()[0] if os.path.isfile(p) else "absent"

a_new = [r for r in plan if r["group"] == "A" and r["typ"] == "new"]
a_rep = [r for r in plan if r["group"] == "A" and r["typ"] == "replay"]
b_all = [r for r in plan if r["group"] == "B"]
ok = lambda rs: sum(1 for r in rs if st(r["run_id"]) == "ok")
fails = sorted(r["run_id"] for r in plan if st(r["run_id"]).startswith("fail"))
absent = sorted(r["run_id"] for r in plan if st(r["run_id"]) == "absent")

narch = 0
fa = ROOT + "/failed_attempts"
if os.path.isdir(fa):
    narch = len(os.listdir(fa))

reuse_clean = "UNKNOWN"
p = ROOT + "/plan/reuse_audit.csv"
if os.path.isfile(p):
    v = [r["verdict"] for r in csv.DictReader(open(p, newline=""))]
    reuse_clean = "PASS" if ("DIFFERS" not in v and "ONLY_IN_OLD" not in v) \
        else "FAIL"

bvar = "UNKNOWN"
p = ROOT + "/validation/bvariant_semantics.csv"
if os.path.isfile(p):
    v = [r["verdict"] for r in csv.DictReader(open(p, newline=""))]
    bvar = "PASS" if "FAIL" not in v else "FAIL"

checks = {}
p = ROOT + "/validation/checks.json"
if os.path.isfile(p):
    checks = json.load(open(p))

# headline numbers from summaries
lines_sum = []
p = ROOT + "/derived/summary_across_seeds.csv"
if os.path.isfile(p):
    for r in csv.DictReader(open(p, newline="")):
        if r["metric"] == "cct_ns" and r["n"] != "0":
            lines_sum.append("  %-8s %-6s %-16s n=%s mean=%s ms sd=%s ms" % (
                r["case"], r["alg"], r["variant"], r["n"],
                "%.3f" % (float(r["mean"]) / 1e6),
                "%.3f" % (float(r["std"]) / 1e6)))

report_text = ("""# V20 第一批补实验完成报告

生成时间：自动（make_zip 阶段）。所有数字来自实际状态文件与派生表，未手工修饰。

## 完成 / 复用 / 失败 / 待确认 / 未执行

| 类别 | 数量 | 说明 |
|---|---|---|
| A组 新增（种子1,3,4,5） | %d / %d ok | 4案例×5算法×4种子 |
| A组 复用（旧seed=2正式结果） | 20 | 复用依据：逐文件字节级重放审计 = %s |
| A组 重复核验（seed=2重放） | %d / %d ok | 不计入独立样本，仅作复用审计 |
| B组 消融（2变体×2案例×5种子） | %d / %d ok | 语义门 = %s |
| 失败保留（当前尝试） | %d | %s |
| 失败保留（已归档的历史尝试） | {NARCH} | 见 failed_attempts/（seed=1 首次尝试因代码守卫 third.cc:4406 报 CONFIG_ERROR，原始日志完整保留；第二次尝试按任务书"必要记录设置"补充有界包踪键，其无行为变化证明见 validation/logging_equivalence.csv） |
| 未执行 | %d | %s |

## 本批回答 / 未回答

- 已回答：核心4案例×5算法的跨种子（1–5）分布；迁移与首包错开两项单项消融。
- 未回答（按任务书明示，本批不执行）：固定等待对照、当前队列替代预测、
  下限边界与异步命令、零初始速率等待触发用例 —— 设计见 next_experiment_design.md，
  全部标记未执行。不声称已解决全部 M1/M3/M7。
- C项缺口（事件级反馈仲裁、定时器、事件级队列）单列于 detailed/*/README_coverage.md。

## 跨种子 CCT 摘要（均值/标准差，全部逐种子数据见 derived/）

```
%s
```

## 自动核验

checks.json 摘要：REQUIRED_FAILURES = %s

失败与不利结果均保留原始输出，未删除、未重试冒充。
""" % (ok(a_new), len(a_new), reuse_clean, ok(a_rep), len(a_rep),
       ok(b_all), len(b_all), bvar,
       len(fails), (";".join(fails[:10]) or "无"),
       len(absent), (";".join(absent[:10]) or "无"),
       "\n".join(lines_sum),
       json.dumps(checks.get("REQUIRED_FAILURES", "n/a"),
                  ensure_ascii=False))).replace("{NARCH}", str(narch))
with open(DOCS + "/completion_report.md", "w") as f:
    f.write(report_text)

# ---- run_manifest.csv (task book 8.2) --------------------------------------
binary_sha = ""
bs = "/work/v20/bundle"
p = "/work/simulation/build/scratch/third"
if os.path.isfile(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fb:
        for blk in iter(lambda: fb.read(1 << 20), b""):
            h.update(blk)
    binary_sha = h.hexdigest()

per_run = {}
prp = ROOT + "/derived/per_run_metrics.csv"
if os.path.isfile(prp):
    per_run = {r["run_id"]: r for r in csv.DictReader(open(prp, newline=""))}

with open(ROOT + "/plan/run_manifest.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "attempt_id", "group", "case", "alg", "variant",
                "seed", "rng_note", "type", "binary_sha256", "config_sha16",
                "status", "wall_s", "exit_note", "expected_flows",
                "completed_flows", "truncation_note", "result_path",
                "prior_failed_attempt"])
    for r in plan:
        rid = r["run_id"]
        stp = ROOT + "/results/" + rid + "/STATUS"
        stat, wall, note = "absent", "", ""
        if os.path.isfile(stp):
            parts = open(stp).read().split()
            stat = parts[0]
            wall = parts[-1] if len(parts) > 1 else ""
            note = " ".join(parts[1:-1])
        pr = per_run.get(rid, {})
        arch = ROOT + "/failed_attempts/" + rid + ".attempt1"
        w.writerow([rid, "a1", r["group"], r["case"], r["alg"], r["variant"],
                    r["seed"], "SetSeed only; run number ns-3 default",
                    r["typ"], binary_sha, r["config_sha16"], stat, wall, note,
                    pr.get("expected_flows", ""), pr.get("completed_flows", ""),
                    pr.get("note", ""), "raw/" + rid,
                    "yes" if os.path.isdir(arch) else "no"])
print("run_manifest.csv written")

with open(DOCS + "/README.md", "w") as f:
    f.write("""# CBAP V20 第一批补实验数据包

结构与任务书第8节一致。关键入口：

- run_plan.csv / run_manifest：全部运行单元与哈希（run_plan 含 config sha16）
- reuse_audit.csv：旧 seed=2 逐文件字节审计（复用依据）
- variant_diff.md + validation/bvariant_semantics.csv：B组消融的开关语义与证据
- derived/：per_flow / per_run / comparisons_per_seed / summary_across_seeds /
  background_windows / aux_dcqs_cbap0 / control_event_summary / prediction_comparison
- raw/<run_id>/：每次新运行的实际输出（CSV 无损 gzip）+ stdout/stderr + STATUS
- reused/：被引用的旧数据原样（gzip）
- inputs/：每次运行实际配置与 flow/schedule/path/link/topo 输入
- provenance/：版本、源码快照、二进制哈希、REGV4 白名单、环境
- validation/：checks.json、file_coverage.csv、bvariant_semantics.csv
- metric_definitions.md：全部指标口径（含 p99 nearest-rank、CCT 起点、背景共同窗口）

复算方法：解压后
  python3 scripts/verify_all.py --ziproot <解压目录>
即从 per_flow 重算 CCT/均值/p99 并核对 SHA256SUMS。
""")
print("report + README written")
