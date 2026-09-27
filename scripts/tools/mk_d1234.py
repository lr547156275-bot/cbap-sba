# -*- coding: utf-8 -*-
# Build the four D arms for the S3 single-seed comparison.
#
#   D1  DCQCN only                                    (baseline)
#   D2  static cap, migration OFF, boost forced 0
#   D3  static cap, migration ON,  boost forced 0     (re-run: binary changed)
#   D4  static cap, migration ON,  queue band ON
#
# D2/D3/D4 are generated from the SAME source config so they can differ only in
# the keys named below; the script asserts that and prints the diff.
# Every arm gets FLOW_TIMING_FILE so the unified FCT/BCT/CCT can be built for
# the baseline too, which is the whole point of item 3.
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
CBAP_SRC = os.path.join(B, 'pa_cap1000_rho090.txt')
DCQCN_SRC = os.path.join(B, 'ckpt2_dcqcn_s3.txt')

ARMS = [
    ('d1_dcqcn', DCQCN_SRC, {}),
    ('d2_caponly', CBAP_SRC, {'CBAP_MIGRATION_ENABLE': '0',
                              'CBAP_QUEUE_BAND_ENABLE': '0'}),
    ('d3_capmig', CBAP_SRC, {'CBAP_MIGRATION_ENABLE': '1',
                             'CBAP_QUEUE_BAND_ENABLE': '0'}),
    ('d4_capmigband', CBAP_SRC, {'CBAP_MIGRATION_ENABLE': '1',
                                 'CBAP_QUEUE_BAND_ENABLE': '1'}),
]


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(txt):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', txt, re.M)
    return m.group(1) if m else None


for tag, src, over in ARMS:
    if not os.path.isfile(src):
        print('MISSING SOURCE %s' % src)
        sys.exit(2)
    t = load(src)
    old = outdir_of(t)
    if not old:
        print('%s: cannot find output dir in %s' % (tag, src))
        sys.exit(2)
    new = '%s_out' % tag
    t = t.replace(old + '/', new + '/')
    # any remaining absolute-ish references to the old dir
    t = t.replace(old, new)

    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if pat.search(t):
            t = pat.sub('%s %s' % (k, v), t)
        else:
            t = t.rstrip('\n') + '\n%s %s\n' % (k, v)

    if not re.search(r'^FLOW_TIMING_FILE\s', t, re.M):
        t = t.rstrip('\n') + '\nFLOW_TIMING_FILE %s/flow_timing.csv\n' % new

    io.open(os.path.join(B, '%s.txt' % tag), 'w',
            encoding='utf-8', errors='surrogateescape').write(t)
    d = os.path.join(B, new)
    if not os.path.isdir(d):
        os.makedirs(d)
    print('wrote %-16s -> %s/  (from %s)' % (tag + '.txt', new,
                                             os.path.basename(src)))

# ---- assert the CBAP arms differ ONLY in the intended keys ----------------
KEYS = ('CBAP_MIGRATION_ENABLE', 'CBAP_QUEUE_BAND_ENABLE')
print('')
print('=== CBAP arms: differences other than output paths and the two flags ===')
base = None
bad = 0
for tag in ('d2_caponly', 'd3_capmig', 'd4_capmigband'):
    t = load(os.path.join(B, '%s.txt' % tag))
    norm = []
    for ln in t.split('\n'):
        w = ln.split()
        if not w:
            continue
        if w[0] in KEYS:
            continue
        if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
            continue
        norm.append(ln.strip())
    if base is None:
        base, basetag = norm, tag
        continue
    only_a = [x for x in base if x not in norm]
    only_b = [x for x in norm if x not in base]
    if only_a or only_b:
        bad += 1
        print('  %s vs %s DIFFERS:' % (basetag, tag))
        for x in only_a[:6]:
            print('    only in %s: %s' % (basetag, x))
        for x in only_b[:6]:
            print('    only in %s: %s' % (tag, x))
    else:
        print('  %s vs %s : identical apart from paths and the two flags' %
              (basetag, tag))

print('')
print('=== per-arm key values (what actually runs) ===')
hdr = '%-16s %-8s %-10s %-9s %-9s %-9s %-6s'
print(hdr % ('arm', 'CC_MODE', 'CBAP_EN', 'STEADYCAP', 'CAP_FRAC', 'MIGRATE',
             'BAND'))
for tag, _, _ in ARMS:
    t = load(os.path.join(B, '%s.txt' % tag))

    def g(k, d='-'):
        m = re.search(r'^%s\s+(\S+)' % k, t, re.M)
        return m.group(1) if m else d
    print(hdr % (tag, g('CC_MODE'), g('CBAP_ENABLE'),
                 g('CBAP_STEADY_CAP_ENABLE'), g('CBAP_STEADY_CAP_FRACTION'),
                 g('CBAP_MIGRATION_ENABLE'), g('CBAP_QUEUE_BAND_ENABLE')))
    print('%18sstop=%s  flow_timing=%s' % ('', g('SIMULATOR_STOP_TIME'),
                                           g('FLOW_TIMING_FILE')))

if bad:
    print('')
    print('ARM CONSTRUCTION FAIL: %d unintended difference(s)' % bad)
    sys.exit(1)
print('')
print('arms OK')
