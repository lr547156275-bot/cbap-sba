#!/usr/bin/env python3
"""V20 batch-1 automatic verification (task book 8.3).

Default mode audits /work/v20 + old dirs.  --ziproot <dir> re-runs the
self-contained subset (SHA256SUMS + derived-table recomputation) inside an
extracted copy of the ZIP, proving the bundle is independently recomputable.
Writes validation/checks.json; exits non-zero if any REQUIRED check fails.
"""
import csv, hashlib, json, math, os, sys

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def recompute_from_per_flow(root):
    """Recompute CCT/mean/p99 from per_flow_metrics and compare per_run."""
    der = os.path.join(root, "derived")
    with open(der + "/per_flow_metrics.csv", newline="") as f:
        pf = list(csv.DictReader(f))
    with open(der + "/per_run_metrics.csv", newline="") as f:
        pr = {r["run_id"]: r for r in csv.DictReader(f)}
    byrun = {}
    for r in pf:
        byrun.setdefault(r["run_id"], []).append(r)
    bad = []
    for rid, rows in byrun.items():
        want = pr.get(rid)
        if not want or want["cct_ns"] == "NA":
            continue
        comp = [r for r in rows if r["complete"] == "1"]
        if len(comp) != int(want["expected_flows"]):
            continue
        cct = max(int(r["last_ack_ns"]) for r in comp) - int(comp[0]["ready_ns"])
        fcts = sorted(int(r["fct_ns"]) for r in comp)
        p99 = fcts[max(0, math.ceil(0.99 * len(fcts)) - 1)]
        mean = sum(fcts) / len(fcts)
        if (cct != int(want["cct_ns"]) or p99 != int(want["p99_fct_ns"]) or
                abs(mean - float(want["mean_fct_ns"])) > 1.0):
            bad.append(rid)
    return len(byrun), bad

checks = {}
req_fail = []

if len(sys.argv) > 2 and sys.argv[1] == "--ziproot":
    root = sys.argv[2]
    n, bad = recompute_from_per_flow(root)
    checks["zip_recompute_runs"] = n
    checks["zip_recompute_mismatches"] = bad
    if bad:
        req_fail.append("recompute mismatch: %s" % bad[:5])
    sums = os.path.join(root, "SHA256SUMS.txt")
    nbad = 0
    with open(sums) as f:
        for ln in f:
            h, rel = ln.strip().split(None, 1)
            p = os.path.join(root, rel.strip())
            if not os.path.isfile(p) or sha256(p) != h:
                nbad += 1
    checks["zip_sha_mismatches"] = nbad
    if nbad:
        req_fail.append("%d SHA mismatches" % nbad)
    print(json.dumps(checks, indent=1))
    sys.exit(1 if req_fail else 0)

ROOT = "/work/v20"
with open(ROOT + "/plan/run_plan.csv", newline="") as f:
    plan = list(csv.DictReader(f))
checks["plan_entries"] = len(plan)
checks["plan_unique_run_ids"] = len(set(r["run_id"] for r in plan))
if checks["plan_entries"] != checks["plan_unique_run_ids"]:
    req_fail.append("duplicate run_ids")
# 120 target units = 100 A + 20 B (A seed2 counted as reused units)
a = [r for r in plan if r["group"] == "A"]
b = [r for r in plan if r["group"] == "B"]
checks["units_A"] = len(a)
checks["units_B"] = len(b)
if len(a) != 100 or len(b) != 20:
    req_fail.append("unit counts wrong")

status = {}
for r in plan:
    d = ROOT + "/results/" + r["run_id"]
    st = "absent"
    if os.path.isfile(d + "/STATUS"):
        st = open(d + "/STATUS").read().split()[0]
    status[r["run_id"]] = st
checks["executed_ok"] = sum(1 for v in status.values() if v == "ok")
checks["executed_fail"] = sorted(
    k for k, v in status.items() if v.startswith("fail"))
checks["not_executed"] = sorted(
    k for k, v in status.items() if v == "absent")
if checks["executed_fail"]:
    req_fail.append("failed runs present (kept, see list)")

# per-run seed column agrees with the plan
with open(ROOT + "/derived/per_run_metrics.csv", newline="") as f:
    per_run = list(csv.DictReader(f))
seedbad = [r["run_id"] for r in per_run
           if r["seed_col_in_csv"] not in ("", r["seed"])]
checks["seed_column_mismatch"] = seedbad
if seedbad:
    req_fail.append("seed column mismatch")

n, bad = recompute_from_per_flow(ROOT)
checks["recompute_runs"] = n
checks["recompute_mismatches"] = bad
if bad:
    req_fail.append("derived recompute mismatch")

for fn, key in (("plan/reuse_audit.csv", "reuse_audit_rows"),
                ("validation/bvariant_semantics.csv", "bvariant_rows"),
                ("derived/background_windows.csv", "bg_rows")):
    p = os.path.join(ROOT, fn)
    checks[key] = sum(1 for _ in open(p)) - 1 if os.path.isfile(p) else -1
    if checks[key] < 0:
        req_fail.append(fn + " missing")
ra = ROOT + "/plan/reuse_audit.csv"
if os.path.isfile(ra):
    with open(ra, newline="") as f:
        v = [r["verdict"] for r in csv.DictReader(f)]
    checks["reuse_differs"] = v.count("DIFFERS") + v.count("ONLY_IN_OLD")
    if checks["reuse_differs"]:
        req_fail.append("reuse audit not clean")

checks["REQUIRED_FAILURES"] = req_fail
os.makedirs(ROOT + "/validation", exist_ok=True)
with open(ROOT + "/validation/checks.json", "w") as f:
    json.dump(checks, f, indent=1, ensure_ascii=False)
print(json.dumps(checks, indent=1, ensure_ascii=False))
print("VERDICT:", "PASS" if not req_fail else "FAIL")
sys.exit(1 if req_fail else 0)
