#!/usr/bin/env python3
"""Byte-level audit of the 20 seed=2 replays against the old formal results.

For every A-group replay run, compare each CSV that exists in BOTH the old
directory and the replay directory by SHA256.  Old files that the replay did
not produce (or vice versa) are listed, never silently ignored.
Writes /work/v20/plan/reuse_audit.csv and exits non-zero on any mismatch.
"""
import csv, hashlib, os, sys

ROOT = "/work/v20"
OLD = "/work/v2_400g/results"
PREF = {"200g_s2": "fm200g_s2", "400g_s2": "fm400g_s2",
        "400g_s3": "fm400g_s3", "400g_s5": "fm400g_s5"}

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

rows, bad = [], 0
with open(ROOT + "/plan/run_plan.csv", newline="") as f:
    plan = [r for r in csv.DictReader(f)
            if r["group"] == "A" and r["typ"] == "replay"]

for r in plan:
    run_id = r["run_id"]
    new_d = "%s/results/%s" % (ROOT, run_id)
    old_d = "%s/%s_%s" % (OLD, PREF[r["case"]], r["alg"])
    if not os.path.isdir(new_d):
        rows.append([run_id, "-", "REPLAY_DIR_MISSING", "", ""])
        bad += 1
        continue
    new_files = {x for x in os.listdir(new_d) if x.endswith(".csv")}
    old_files = {x for x in os.listdir(old_d) if x.endswith(".csv")}
    for fn in sorted(new_files | old_files):
        po, pn = os.path.join(old_d, fn), os.path.join(new_d, fn)
        if fn not in old_files:
            rows.append([run_id, fn, "ONLY_IN_REPLAY", "", sha(pn)[:16]])
            continue                      # informational, not a failure
        if fn not in new_files:
            rows.append([run_id, fn, "ONLY_IN_OLD", sha(po)[:16], ""])
            bad += 1
            continue
        so, sn = sha(po), sha(pn)
        st = "IDENTICAL" if so == sn else "DIFFERS"
        if st == "DIFFERS":
            bad += 1
        rows.append([run_id, fn, st, so[:16], sn[:16]])

os.makedirs(ROOT + "/plan", exist_ok=True)
with open(ROOT + "/plan/reuse_audit.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["run_id", "file", "verdict", "old_sha16", "replay_sha16"])
    w.writerows(rows)

n_id = sum(1 for x in rows if x[2] == "IDENTICAL")
n_df = sum(1 for x in rows if x[2] == "DIFFERS")
n_oo = sum(1 for x in rows if x[2] == "ONLY_IN_OLD")
n_or = sum(1 for x in rows if x[2] == "ONLY_IN_REPLAY")
print("reuse audit: identical=%d differs=%d only_old=%d only_replay=%d"
      % (n_id, n_df, n_oo, n_or))
print("VERDICT:", "PASS - old seed=2 results are byte-reproducible, reuse "
      "justified" if bad == 0 else "FAIL - do NOT pool old seed2 with new "
      "runs; see reuse_audit.csv")
sys.exit(0 if bad == 0 else 1)
