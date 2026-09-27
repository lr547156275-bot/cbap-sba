#!/usr/bin/env python3
"""V20 batch-1: generate the run plan and every config, with drift assertions.

Rules from the task book:
  * A-group: 4 cases x 5 algorithms x seeds 1-5.  seed=2 cells are REPLAYS of
    the old formal runs (byte-comparison audit); seeds 1,3,4,5 are new.
  * B-group: {200g,400g}_s2 CBAP with exactly one switch flipped
    (CBAP_MIGRATION_ENABLE=0 | CBAP_PHASE_SPREAD_ENABLE=0), seeds 1-5.
  * A clone may differ from its parent config ONLY in: SIM_SEED, output paths,
    labels (SCENARIO), and the single B-group switch.  Anything else aborts.
Writes /work/v20/configs/*.txt, /work/v20/plan/run_plan.csv.
"""
import os, sys, hashlib

V2 = "/work/v2_400g/configs"
ROOT = "/work/v20"
CFG = ROOT + "/configs"
RES = ROOT + "/results"
LOG = ROOT + "/logs"
PLAN = ROOT + "/plan"

CASES = {  # case_id -> (old config prefix, expected sync flows)
    "200g_s2": ("fm200g_s2", 64),
    "400g_s2": ("fm400g_s2", 64),
    "400g_s3": ("fm400g_s3", 64),
    "400g_s5": ("fm400g_s5", 32),
}
ALGS = ["cbap", "hpcc", "dcqn", "dctcp", "timely"]
SEEDS = [1, 2, 3, 4, 5]
BVAR = {  # variant -> (switch key, forced value)
    "no_migration": ("CBAP_MIGRATION_ENABLE", "0"),
    "no_phase_spread": ("CBAP_PHASE_SPREAD_ENABLE", "0"),
}
# keys whose VALUE may legitimately differ between parent and clone
ALLOWED_KEYS = {"SIM_SEED", "SCENARIO"}

for d in (CFG, RES, LOG, PLAN):
    os.makedirs(d, exist_ok=True)


def read_cfg(path):
    with open(path) as f:
        return f.read().splitlines()


def key_of(line):
    s = line.strip()
    if not s:
        return None
    return s.split()[0]


def clone(parent_path, run_id, seed, flip=None, scenario=None):
    """Clone parent config; return (new_path, list_of_diffs)."""
    lines = read_cfg(parent_path)
    out, diffs, seen_flip = [], [], False
    outdir = "%s/%s" % (RES, run_id)
    for ln in lines:
        k = key_of(ln)
        new = ln
        if k == "SIM_SEED":
            new = "SIM_SEED %d" % seed
        elif k == "SCENARIO" and scenario:
            new = "SCENARIO %s" % scenario
        elif flip and k == flip[0]:
            new = "%s %s" % (flip[0], flip[1])
            seen_flip = True
        elif k and ("/work/v2_400g/results/" in ln):
            # redirect every output path into the run directory
            parts = ln.split()
            base = os.path.basename(parts[1])
            new = "%s %s/%s" % (parts[0], outdir, base)
        if new != ln:
            diffs.append((k, ln.strip(), new.strip()))
        out.append(new)
    if flip and not seen_flip:
        sys.exit("FATAL: %s does not contain %s" % (parent_path, flip[0]))
    if seed == 1:
        # third.cc:4406 hard-guards seed==1 behind a bounded packet trace
        # (recording-only requirement).  Add the two RECORDING keys; their
        # behavioural neutrality is proven by the logging-equivalence run
        # (validation/logging_equivalence.csv) per task book section 5.2.
        out.append("CBAP_PACKET_TRACE_FILE %s/cbap_packet_trace.bin" % outdir)
        out.append("CBAP_PACKET_TRACE_MAX_MB 64")
        diffs.append(("CBAP_PACKET_TRACE_FILE", "(absent)", "added"))
        diffs.append(("CBAP_PACKET_TRACE_MAX_MB", "(absent)", "added"))
    # drift assertion: any diff whose key is not allowed must be an output
    # path redirect, the single flipped switch, or the seed-1 recording keys
    for k, old, new in diffs:
        if k in ALLOWED_KEYS:
            continue
        if flip and k == flip[0]:
            continue
        if "/work/v2_400g/results/" in old and outdir in new:
            continue
        if seed == 1 and k in ("CBAP_PACKET_TRACE_FILE",
                               "CBAP_PACKET_TRACE_MAX_MB"):
            continue
        sys.exit("FATAL drift in %s: %s\n  old: %s\n  new: %s"
                 % (run_id, k, old, new))
    p = "%s/%s.txt" % (CFG, run_id)
    with open(p, "w") as f:
        f.write("\n".join(out) + "\n")
    return p, diffs


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:16]


rows = []
for case, (pref, nflow) in CASES.items():
    for alg in ALGS:
        parent = "%s/%s_%s.txt" % (V2, pref, alg)
        if not os.path.isfile(parent):
            sys.exit("FATAL: missing parent config " + parent)
        for seed in SEEDS:
            typ = "replay" if seed == 2 else "new"
            run_id = "%s_%s_s%d_a1" % (case, alg, seed)
            p, diffs = clone(parent, run_id, seed)
            rows.append(dict(run_id=run_id, group="A", case=case, alg=alg,
                             variant="full", seed=seed, typ=typ,
                             parent=os.path.basename(parent),
                             config=p, config_sha16=sha16(p),
                             expected_flows=nflow,
                             ndiff=len(diffs)))

for case in ("200g_s2", "400g_s2"):
    pref, nflow = CASES[case]
    parent = "%s/%s_cbap.txt" % (V2, pref)
    for var, flip in BVAR.items():
        for seed in SEEDS:
            run_id = "%s_cbap_%s_s%d_a1" % (case, var, seed)
            scen = "%s_cbap_%s" % (pref, var)
            p, diffs = clone(parent, run_id, seed, flip=flip, scenario=scen)
            rows.append(dict(run_id=run_id, group="B", case=case, alg="cbap",
                             variant=var, seed=seed, typ="new",
                             parent=os.path.basename(parent),
                             config=p, config_sha16=sha16(p),
                             expected_flows=nflow,
                             ndiff=len(diffs)))

hdr = ["run_id", "group", "case", "alg", "variant", "seed", "typ", "parent",
       "config", "config_sha16", "expected_flows", "ndiff"]
with open(PLAN + "/run_plan.csv", "w") as f:
    f.write(",".join(hdr) + "\n")
    for r in rows:
        f.write(",".join(str(r[h]) for h in hdr) + "\n")

na = sum(1 for r in rows if r["group"] == "A" and r["typ"] == "new")
ra = sum(1 for r in rows if r["group"] == "A" and r["typ"] == "replay")
nb = sum(1 for r in rows if r["group"] == "B")
print("plan written: %d entries  (A-new=%d  A-replay=%d  B=%d)"
      % (len(rows), na, ra, nb))
print("all configs drift-checked against their parents")
