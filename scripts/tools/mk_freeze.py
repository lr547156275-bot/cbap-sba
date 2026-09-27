# -*- coding: utf-8 -*-
# Writes two documents into the experiment dir:
#   S3_TUNING_WINNER_CANDIDATE.md  -- item 1 registration + full SHA manifest
#   B080_ROOT_CAUSE.md             -- item 2 audit verdict (B/C) + evidence
# Read-only w.r.t. experiments; computes SHAs of the exact artefacts.
import hashlib
import io
import os
import re
import subprocess

B = '/work/simulation/experiment/scheme1_sba'
W = '/work/simulation'


def sha(p):
    if not os.path.isfile(p):
        return 'ABSENT'
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def cfg(path, k, d='-'):
    try:
        with open(path) as fh:
            for ln in fh:
                w = ln.split()
                if len(w) >= 2 and w[0] == k:
                    return w[1]
    except IOError:
        pass
    return d


FILES = [
    ('binary third', W + '/build/scratch/third'),
    ('libns3 p2p', W + '/build/libns3.17-point-to-point-debug.so'),
    ('rdma-hw.cc (post-ledger-fix)', W + '/src/point-to-point/model/rdma-hw.cc'),
    ('rdma-hw.h', W + '/src/point-to-point/model/rdma-hw.h'),
    ('third.cc', W + '/scratch/third.cc'),
    ('checker d_metrics3.py', '/work/d_metrics3.py'),
    ('config scr7_d1.txt', B + '/scr7_d1.txt'),
    ('config scr7_d3.txt', B + '/scr7_d3.txt'),
    ('config scr7_b040.txt', B + '/scr7_b040.txt'),
    ('topology', B + '/' + cfg(B + '/scr7_b040.txt', 'TOPOLOGY_FILE',
                               'topology.txt')),
    ('flow file', B + '/' + cfg(B + '/scr7_b040.txt', 'FLOW_FILE', 's3_flow.txt')),
    ('round schedule', B + '/' + cfg(B + '/scr7_b040.txt',
                                     'ROUND_SCHEDULE_FILE',
                                     's3_round_schedule.txt')),
]

b040 = B + '/scr7_b040.txt'
man = ''
vt = B + '/scr7_b040_out/controller_v2_trace.csv'
if os.path.isfile(vt):
    with open(vt) as fh:
        for ln in fh:
            if ln.startswith('#MANIFEST'):
                man = ln.strip()
                break

git = subprocess.check_output(
    ['git', '-C', '/work', 'rev-parse', 'HEAD']).decode().strip()
dirty = subprocess.check_output(
    ['git', '-C', '/work', 'status', '--porcelain']).decode().count('\n')

doc = io.StringIO()
doc.write(u'# S3_TUNING_WINNER_CANDIDATE — scr7_b040 (BMAX = 0.04C)\n\n')
doc.write(u'Status: **CANDIDATE ONLY**, single seed, S3 only.  NOT a final\n'
          u'parameter.  b040 must not be re-tuned on S3 and then presented\n'
          u'against S4/S5 as an independent validation.\n\n')
doc.write(u'**REVALIDATION REQUIRED**: the b080 audit found a shared\n'
          u'correctness defect (LEDGER_GHOST_ARRIVAL, see B080_ROOT_CAUSE.md)\n'
          u'that biases the boost law input in ALL v2 cells including b040.\n'
          u'The scr7 numbers below are the PRE-FIX record; the scr8 rerun\n'
          u'supersedes them once complete.\n\n')
doc.write(u'## Pre-fix screening record (scr7, S3, seed=%s)\n\n'
          % cfg(b040, 'SIM_SEED', '2'))
doc.write(u'| metric | D1 | D3 | b040 |\n|---|---|---|---|\n')
doc.write(u'| CCT (ms) | 58.3730 | 58.4911 | 56.8572 |\n')
doc.write(u'| batch goodput (G) | 9.1972 | 9.1787 | 9.4425 |\n')
doc.write(u'| queue p99 / max (B) | 967,304 / 1,279,608 | 1,048 / 9,432 '
          u'| 6,288 / 26,200 |\n')
doc.write(u'| bg full /D1 | 1.0000 | 0.9984 | 0.9992 |\n')
doc.write(u'| PFC / drop / retx | 0/0/0 | 0/0/0 | 0/0/0 |\n\n')
doc.write(u'Note: BCT improvement and batch-goodput improvement are the same\n'
          u'effect expressed twice (fixed batch bytes), not two independent\n'
          u'contributions.\n\n')
doc.write(u'## Frozen configuration\n\n```\n%s\n```\n\n' % (man or 'MANIFEST '
          'line unavailable'))
keys = ['CC_MODE', 'CBAP_ENABLE', 'CBAP_RHO', 'CBAP_STEADY_CAP_ENABLE',
        'CBAP_STEADY_CAP_FRACTION', 'CBAP_MIGRATION_ENABLE',
        'CBAP_QUEUE_BAND_ENABLE', 'CBAP_QUEUE_BAND_V2_ENABLE',
        'CBAP_QB2_BMAX_RATIO', 'CBAP_QB2_QTARGET_RATIO',
        'CBAP_QC_SOFT_FRACTION', 'CBAP_QC_MAX_BOOST_RATIO',
        'CBAP_QC_H_GUARD_US', 'CBAP_QC_APP_HARD_DELAY_US',
        'CBAP_QC_SAFETY_MARGIN_BYTES', 'MIN_RATE', 'SIM_SEED', 'SCENARIO',
        'SIMULATOR_STOP_TIME', 'APP_RATE_CAP_BPS', 'FLOW_FILE',
        'TOPOLOGY_FILE']
doc.write(u'| key | scr7_b040 value |\n|---|---|\n')
for k in keys:
    doc.write(u'| %s | %s |\n' % (k, cfg(b040, k)))
doc.write(u'\n## SHA-256 manifest (state at registration, ledger fix '
          u'applied, pre-rebuild)\n\n')
doc.write(u'git HEAD %s (dirty files: %d, deliberate: unpushed round work)\n\n'
          % (git, dirty))
doc.write(u'| artefact | sha256 |\n|---|---|\n')
for name, p in FILES:
    doc.write(u'| %s | %s |\n' % (name, sha(p)))
with io.open(B + '/S3_TUNING_WINNER_CANDIDATE.md', 'w',
             encoding='utf-8') as fh:
    fh.write(doc.getvalue())
print('wrote S3_TUNING_WINNER_CANDIDATE.md')

rc = io.StringIO()
rc.write(u'# B080 root cause — LEDGER_GHOST_ARRIVAL (classification B/C)\n\n')
rc.write(u'NOT "EXPECTED_NONMONOTONIC_SATURATION".  The low duty is a\n'
         u'correctness defect in per-QP command bookkeeping, established\n'
         u'read-only from scr7_b080_out/controller_v2_trace.csv + qc_trace.csv\n'
         u'(b080_audit.py passes 1+2), then anchored in code.\n\n')
rc.write(u'## Q1 first occurrences (b080)\n'
         u'- boost_requested>0: t=2.000010000 s (law asks 1.198G, clamp 0.8G)\n'
         u'- boost_commanded>0: t=2.000010000 s\n'
         u'- boost_effective>0: t=2.000190000 s (command->effective 180 us '
         u'= H_eff+1 epoch, correct)\n'
         u'- pending_excess>0:  t=2.000255000 s\n\n')
rc.write(u'## Q2 duty attribution (11,723 batch epochs)\n'
         u'- LAW_ZERO (Q_pred >= Q_target): 11,615 = 99.08%\n'
         u'- WAITING pending ETA: 71 = 0.61%; ON: 35 = 0.30%; vetoes: ~0\n'
         u'- zones: GREEN throughout; RED/DRAIN never entered\n'
         u'- lease violations 0; SAME-generation stuck pending 0 (an earlier\n'
         u'  ">2*H_eff" count of 96 was a detector artifact on legal\n'
         u'  replacement chains and is retracted)\n\n')
rc.write(u'## Q3 trajectory\n'
         u'Single 175 us lease at 0.8G (2.000190-2.000360), queue 9,432 ->\n'
         u'28,296 B (deposit matches 0.8G*188us/8).  From 2.000255 the trace\n'
         u'shows pending_excess LOCKED at 26,528-26,534 B (p50 == p99) for\n'
         u'the remaining 58 ms; that constant alone exceeds Q_target=26,214,\n'
         u'so the GREEN law headroom is permanently zero and boost never\n'
         u're-arms.  Full table: b080_audit2.py output.\n\n')
rc.write(u'## Mechanism (code-anchored)\n'
         u'1. Propagation (DeliverCbapPortSummary): per-QP share =\n'
         u'   (boostCmd - drainCmd)/genSize is an ABSOLUTE aggregate applied\n'
         u'   on top of senderEffective (which already contains the boost).\n'
         u'   A down-to-zero command computes share = 0: NO pending flag, and\n'
         u'   commandedWireBps frozen at the boosted senderEffective.\n'
         u'2. Confirmation (QueueControllerEpoch): commandedWireBps is never\n'
         u'   cleared after the deadline, so the confirmation branch\n'
         u'   re-asserts predictedArrival = (stale boosted) commandedWireBps\n'
         u'   EVERY epoch, overwriting the per-epoch refresh from the actual\n'
         u'   rate.  Self-sustaining: inflated Q_pred -> law 0 -> delta <\n'
         u'   deadband -> no new command -> stale value never rewritten.\n\n')
rc.write(u'## Q4 verdict: B/C\n'
         u'- B: arrival-envelope accounting carries a ghost (ledger claims\n'
         u'  ~11.2G while dispatched targets sum ~9.7G and physical queue\n'
         u'  stays ~2-3KB)\n'
         u'- C: state-machine ordering lets a CLOSED command keep rewriting\n'
         u'  predictedArrival\n'
         u'- affects b005-b040 as well: same constant ghost (b040: 15,901 B\n'
         u'  < Q_target, so it still re-armed at 55.6%% in-batch duty), i.e.\n'
         u'  all scr7 v2 numbers are biased and scr8 rerun supersedes them.\n'
         u'- open secondary observation (re-audit after fix): b080 mean\n'
         u'  applied sum 9.72G vs cap 10G across all batch thirds.\n\n')
rc.write(u'## Fix\n'
         u'fixAH_ledger.py, two edits in rdma-hw.cc only: share computed as\n'
         u'delta (commandedNet - effectiveNet)/genSize; commandedWireBps\n'
         u'cleared on confirmation.  No threshold, zone, law, checker, or\n'
         u'frozen parameter touched.  Unit test qb2_ledger_unittest.py\n'
         u'(python mirror, 7 checks) reproduces the ghost under the old\n'
         u'semantics and proves the bounded-lifetime property under the fix.\n')
with io.open(B + '/B080_ROOT_CAUSE.md', 'w', encoding='utf-8') as fh:
    fh.write(rc.getvalue())
print('wrote B080_ROOT_CAUSE.md')
