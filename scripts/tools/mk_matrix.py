# -*- coding: utf-8 -*-
# Final 30-cell matrix: 5 algorithms x 6 scenarios, one seed (determinism
# proven).  Baselines run their STANDARD frozen configs -- no threshold is
# tuned toward any target gap.  b040 enters with its frozen config verbatim.
#
# Trace slimming (uniform across ALL 30 cells): CBAP_QC_TRACE_FILE and
# TX_SERIALIZATION_TRACE_FILE are removed (both provably guarded when unset);
# QLEN_MON_FILE is pointed at /dev/null instead of removed, because
# third.cc:5024 fopen()s it with NO null guard and the monitor is scheduled
# unconditionally -- removing the key segfaulted all 30 cells (rc=139, the
# 2026-08-20 22:xx run).  With /dev/null the monitor runs on the exact same
# schedule as the twins and discards the bytes, so every retained output file
# must stay byte-identical to its scr8/s4v/s5v twin -- matrix_metrics
# verifies exactly that as a free regression.
import hashlib
import io
import os
import re
import subprocess
import sys

B = '/work/simulation/experiment/scheme1_sba'
SLIM = ('CBAP_QC_TRACE_FILE', 'TX_SERIALIZATION_TRACE_FILE')
ALGOS = [('dcqcn', '1'), ('dctcp', '8'), ('timely', '7'), ('hpcc', '3'),
         ('cbapsba', None)]
SCEN = ['s1', 's2', 's6', 's3', 's4', 's5']

DELTA = {
    's1': {'FLOW_FILE': 's1_flow.txt', 'SIMULATOR_STOP_TIME': '2.1',
           'QLEN_MON_START': '1900000000', 'QLEN_MON_END': '2100000000',
           'ROUND_SCHEDULE_FILE': 's1_round_schedule.txt',
           'CBAP_LINK_FILE': 's1_cbap_link.txt',
           'CBAP_PATH_FILE': 's1_cbap_path.txt',
           'SCENARIO': 's1_fan16_256k_bg80',
           'FINAL_COLLECTIVE_FLOW_COUNT': '16'},
    's2': {'FLOW_FILE': 's2_flow.txt', 'SIMULATOR_STOP_TIME': '2.5',
           'QLEN_MON_END': '2500000000',
           'ROUND_SCHEDULE_FILE': 's2_round_schedule.txt',
           'CBAP_LINK_FILE': 's2_cbap_link.txt',
           'CBAP_PATH_FILE': 's2_cbap_path.txt',
           'SCENARIO': 's2_fan64_256k_bg80'},
    's6': {'FLOW_FILE': 's6_flow.txt', 'SIMULATOR_STOP_TIME': '2.5',
           'QLEN_MON_END': '2500000000',
           'ROUND_SCHEDULE_FILE': 's6_round_schedule.txt',
           'ROUND_TRACE_SELECTED_LINKS': '84:1,83:1',
           'CBAP_LINK_FILE': 's6_cbap_link.txt',
           'CBAP_PATH_FILE': 's6_cbap_path.txt',
           'SCENARIO': 's6_dual_bottleneck_256k_bg80',
           'FINAL_COLLECTIVE_FLOW_COUNT': '60',
           'APP_RATE_CAP_FLOW': '0,1'},
    's3': {},
    's4': {'FLOW_FILE': 's4_flow.txt', 'SIMULATOR_STOP_TIME': '5.5',
           'QLEN_MON_END': '5500000000',
           'ROUND_SCHEDULE_FILE': 's4_round_schedule.txt',
           'CBAP_LINK_FILE': 's4_cbap_link.txt',
           'CBAP_PATH_FILE': 's4_cbap_path.txt',
           'SCENARIO': 's4_fan64_1m_bg95',
           'APP_RATE_CAP_BPS': '9500000000'},
    's5': {'FLOW_FILE': 's5_flow.txt', 'SIMULATOR_STOP_TIME': '6.0',
           'QLEN_MON_END': '6000000000',
           'ROUND_SCHEDULE_FILE': 's5_round_schedule.txt',
           'CBAP_LINK_FILE': 's5_cbap_link.txt',
           'CBAP_PATH_FILE': 's5_cbap_path.txt',
           'SCENARIO': 's5_fan64_4m_bg80',
           'APP_RATE_CAP_BPS': '8000000000'},
}


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(t):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M)
    return m.group(1) if m else None


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


made = []
bad = 0
for sc in SCEN:
    for algo, cc in ALGOS:
        tag = 'mx_%s_%s' % (sc, algo)
        if algo == 'cbapsba':
            src = 'scr8_b040.txt'
            over = dict(DELTA[sc])
        else:
            src = 'ckpt2_dcqcn_%s.txt' % sc
            over = {'CC_MODE': cc, 'ALGORITHM': algo}
        t = load(os.path.join(B, src))
        old = outdir_of(t)
        new = '%s_out' % tag
        t = t.replace(old + '/', new + '/').replace(old, new)
        for k, v in over.items():
            pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
            if not pat.search(t):
                print('%s: key %s absent in %s' % (tag, k, src))
                sys.exit(2)
            t = pat.sub('%s %s' % (k, v), t)
        # uniform slimming
        for k in SLIM:
            t = re.sub(r'^%s\s+.*\n' % re.escape(k), '', t, flags=re.M)
        # qlen monitor MUST keep a writable file (unguarded fopen at
        # third.cc:5024); /dev/null keeps the schedule, discards the bytes.
        t = re.sub(r'^QLEN_MON_FILE\s+.*$', 'QLEN_MON_FILE /dev/null', t,
                   flags=re.M)
        if not re.search(r'^FLOW_TIMING_FILE\s', t, re.M):
            t = t.rstrip('\n') + '\nFLOW_TIMING_FILE %s/flow_timing.csv\n' % new
        io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
                errors='surrogateescape').write(t)
        d = os.path.join(B, new)
        if not os.path.isdir(d):
            os.makedirs(d)
        made.append(tag)

# ---- construction checks ---------------------------------------------------
print('=== construction checks ===')
for sc in SCEN:
    tag = 'mx_%s_cbapsba' % sc
    keys = set(DELTA[sc]) | set(SLIM) | {'FLOW_TIMING_FILE', 'QLEN_MON_FILE'}

    def norm(txt):
        out = []
        for ln in txt.split('\n'):
            w = ln.split()
            if not w or w[0] in keys:
                continue
            if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
                continue
            out.append(ln.strip())
        return out
    a = norm(load(os.path.join(B, 'scr8_b040.txt')))
    b2 = norm(load(os.path.join(B, '%s.txt' % tag)))
    extra = [x for x in a if x not in b2] + [x for x in b2 if x not in a]
    if extra:
        bad += 1
        print('  %s DIFFERS beyond intent: %s' % (tag, extra[:4]))
    else:
        print('  %s: frozen b040 + scenario keys + slimming only' % tag)

for sc in ('s3',):
    for algo, cc in ALGOS[:4]:
        tag = 'mx_%s_%s' % (sc, algo)
        t = load(os.path.join(B, '%s.txt' % tag))
        m = re.search(r'^CC_MODE\s+(\S+)', t, re.M)
        assert m.group(1) == cc, tag
print('  baseline CC_MODE spot-checks OK (standard configs, untuned)')

# ---- manifest ---------------------------------------------------------------
man = io.open(B + '/matrix_manifest.txt', 'w', encoding='utf-8')
man.write('# 30-cell matrix manifest\n')
man.write('binary %s\n' % sha('/work/simulation/build/scratch/third'))
head = subprocess.check_output(['git', '-C', '/work', 'rev-parse',
                                'HEAD']).decode().strip()
dirty = subprocess.check_output(['git', '-C', '/work', 'status',
                                 '--porcelain']).decode().count('\n')
man.write('git %s dirty_files %d (unpushed round work, deliberate)\n'
          % (head, dirty))
for fn in sorted(set(sum([[DELTA[s].get('FLOW_FILE', 's3_flow.txt'),
                           DELTA[s].get('ROUND_SCHEDULE_FILE',
                                        's3_round_schedule.txt'),
                           DELTA[s].get('CBAP_LINK_FILE', 's3_cbap_link.txt'),
                           DELTA[s].get('CBAP_PATH_FILE', 's3_cbap_path.txt')]
                          for s in SCEN], ['topology.txt']))):
    p = os.path.join(B, fn)
    if os.path.isfile(p):
        man.write('scenario_file %s %s\n' % (fn, sha(p)))
for tag in made:
    man.write('cell %s %s\n' % (tag, sha(os.path.join(B, '%s.txt' % tag))))
man.close()
print('wrote matrix_manifest.txt (%d cells)' % len(made))
if bad:
    sys.exit(1)
print('')
print('30 matrix cells OK -- baselines standard, b040 frozen, slimming uniform')

