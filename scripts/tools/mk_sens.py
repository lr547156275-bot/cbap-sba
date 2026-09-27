# -*- coding: utf-8 -*-
# Sensitivity annex (NEVER merged into the main matrix):
#   Group A ENV_SENSITIVITY: BUFFER_SIZE 8 -> 2 MB, S3, ALL five algorithms
#     (environment applied uniformly; pre-registered expectation: baseline
#     ~1.28 MB queues now hit PFC/drop territory, CBAP ~26 KB unaffected).
#   Group B ECN_SENSITIVITY: KMIN 400->100, KMAX 1600->400 on S3 for
#     dcqcn / dctcp / cbapsba (honestly labelled baseline variants; whatever
#     numbers come out are reported -- nothing is calibrated to any target).
# All cells derive from the corresponding mx_s3_* configs; the diff is
# verified to be exactly the intended keys + output paths.
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
CELLS = []
for a in ('dcqcn', 'dctcp', 'timely', 'hpcc', 'cbapsba'):
    CELLS.append(('sx_a_%s' % a, 'mx_s3_%s.txt' % a,
                  {'BUFFER_SIZE': '2'}))
for a in ('dcqcn', 'dctcp', 'cbapsba'):
    CELLS.append(('sx_b_%s' % a, 'mx_s3_%s.txt' % a,
                  {'KMIN_MAP': '1 10000000000 100',
                   'KMAX_MAP': '1 10000000000 400'}))


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


bad = 0
for tag, src, over in CELLS:
    sp = os.path.join(B, src)
    if not os.path.isfile(sp):
        print('MISSING %s' % sp)
        sys.exit(2)
    t = load(sp)
    old = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M).group(1)
    new = '%s_out' % tag
    t = t.replace(old + '/', new + '/').replace(old, new)
    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if not pat.search(t):
            print('%s: key %s absent in %s' % (tag, k, src))
            sys.exit(2)
        t = pat.sub('%s %s' % (k, v), t)
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(t)
    if not os.path.isdir(os.path.join(B, new)):
        os.makedirs(os.path.join(B, new))
    # verify: only intended keys + paths differ from the matrix source

    def norm(txt, keys):
        out = []
        for ln in txt.split('\n'):
            w = ln.split()
            if not w or w[0] in keys:
                continue
            if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')
                                or w[1] == '/dev/null'):
                continue
            out.append(ln.strip())
        return out
    a1 = norm(load(sp), set(over))
    b1 = norm(load(os.path.join(B, '%s.txt' % tag)), set(over))
    extra = [x for x in a1 if x not in b1] + [x for x in b1 if x not in a1]
    if extra:
        bad += 1
        print('%s DIFFERS beyond intent: %s' % (tag, extra[:4]))
    else:
        print('wrote %-14s = %s + %s' % (tag, src,
                                         ','.join(sorted(over))))
if bad:
    sys.exit(1)
print('')
print('8 sensitivity cells OK (main matrix untouched)')
