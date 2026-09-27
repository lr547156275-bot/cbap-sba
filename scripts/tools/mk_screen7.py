# -*- coding: utf-8 -*-
# Build the 7-cell D4v2 screening matrix (S3, single seed, serial).
#   1 scr7_d1    DCQCN                      (rerun in a FRESH outdir)
#   2 scr7_d3    static cap + migration     (rerun in a FRESH outdir)
#   3 scr7_b005  D4v2 BMAX=0.005C Qt=0.025*Q_abs
#   4 scr7_b010  D4v2 BMAX=0.010C
#   5 scr7_b020  D4v2 BMAX=0.020C
#   6 scr7_b040  D4v2 BMAX=0.040C
#   7 scr7_b080  D4v2 BMAX=0.080C
# Nothing existing is modified or deleted.  v2 cells are generated from the
# SAME d3 source and asserted to differ ONLY in the four QB2 keys + paths.
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
D1_SRC = os.path.join(B, 'd1_dcqcn.txt')
D3_SRC = os.path.join(B, 'd3_capmig.txt')

QB2_KEYS = ('CBAP_QUEUE_BAND_V2_ENABLE', 'CBAP_QB2_BMAX_RATIO',
            'CBAP_QB2_QTARGET_RATIO', 'CBAP_QB2_TRACE_FILE')

CELLS = [
    ('scr7_d1', D1_SRC, {}),
    ('scr7_d3', D3_SRC, {}),
]
for bm in ('0.005', '0.010', '0.020', '0.040', '0.080'):
    tag = 'scr7_b%s' % bm.replace('0.', '').rstrip()
    CELLS.append((tag, D3_SRC, {
        'CBAP_QUEUE_BAND_V2_ENABLE': '1',
        'CBAP_QB2_BMAX_RATIO': bm,
        'CBAP_QB2_QTARGET_RATIO': '0.025',
        'CBAP_QB2_TRACE_FILE': '%s_out/controller_v2_trace.csv' % tag,
    }))


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(txt):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', txt, re.M)
    return m.group(1) if m else None


for src in (D1_SRC, D3_SRC):
    if not os.path.isfile(src):
        print('MISSING SOURCE %s' % src)
        sys.exit(2)

# d3 must have v1 band OFF -- D4v2 baseline plan is exactly D3
d3txt = load(D3_SRC)
m = re.search(r'^CBAP_QUEUE_BAND_ENABLE\s+(\S+)', d3txt, re.M)
if not m or m.group(1) != '0':
    print('FAIL: d3_capmig.txt does not pin CBAP_QUEUE_BAND_ENABLE 0')
    sys.exit(2)

for tag, src, over in CELLS:
    txt = load(src)
    old = outdir_of(txt)
    if not old:
        print('%s: no output dir found in %s' % (tag, src))
        sys.exit(2)
    new = '%s_out' % tag
    txt = txt.replace(old + '/', new + '/').replace(old, new)
    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if pat.search(txt):
            txt = pat.sub('%s %s' % (k, v), txt)
        else:
            txt = txt.rstrip('\n') + '\n%s %s\n' % (k, v)
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(txt)
    d = os.path.join(B, new)
    if not os.path.isdir(d):
        os.makedirs(d)
    print('wrote %-14s -> %s/  (from %s)'
          % (tag + '.txt', new, os.path.basename(src)))

# ---- assert v2 cells differ from scr7_d3 ONLY in QB2 keys + paths --------
print('')
print('=== diff check: each v2 cell vs scr7_d3 ===')


def norm(txt):
    out = []
    for ln in txt.split('\n'):
        w = ln.split()
        if not w:
            continue
        if w[0] in QB2_KEYS:
            continue
        if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
            continue
        out.append(ln.strip())
    return out


base = norm(load(os.path.join(B, 'scr7_d3.txt')))
bad = 0
for tag, src, over in CELLS:
    if not over:
        continue
    cur = norm(load(os.path.join(B, '%s.txt' % tag)))
    oa = [x for x in base if x not in cur]
    ob = [x for x in cur if x not in base]
    if oa or ob:
        bad += 1
        print('  %s DIFFERS beyond QB2+paths:' % tag)
        for x in (oa + ob)[:8]:
            print('    %s' % x)
    else:
        print('  %-12s identical to scr7_d3 apart from QB2 keys + paths' % tag)

print('')
print('=== per-cell key values ===')
hdr = '%-12s %-8s %-8s %-9s %-7s %-7s %-8s %-8s'
print(hdr % ('cell', 'CC_MODE', 'STEADY', 'CAP_FRAC', 'MIG', 'BANDv1',
             'QB2', 'BMAX'))
for tag, src, over in CELLS:
    txt = load(os.path.join(B, '%s.txt' % tag))

    def g(k, d='-'):
        mm = re.search(r'^%s\s+(\S+)' % k, txt, re.M)
        return mm.group(1) if mm else d
    print(hdr % (tag, g('CC_MODE'), g('CBAP_STEADY_CAP_ENABLE'),
                 g('CBAP_STEADY_CAP_FRACTION'), g('CBAP_MIGRATION_ENABLE'),
                 g('CBAP_QUEUE_BAND_ENABLE'), g('CBAP_QUEUE_BAND_V2_ENABLE'),
                 g('CBAP_QB2_BMAX_RATIO')))

if bad:
    print('')
    print('CELL CONSTRUCTION FAIL: %d unintended difference(s)' % bad)
    sys.exit(1)
print('')
print('7 cells OK')
