# -*- coding: utf-8 -*-
# Round cells:
#   Neighborhood (item 2): nb_b030 / nb_b050 from scr8_b040.txt, changing ONLY
#     CBAP_QB2_BMAX_RATIO (+ output paths).  b040 itself is NOT re-run: the
#     binary is unchanged since scr8 and the sim is deterministic, so
#     scr8_b040 IS the b040 point (its sha manifest already frozen).
#   HPCC (item 3): hp_s3 / hp_s4 / hp_s5 from the corresponding DCQCN cells,
#     changing ONLY CC_MODE 1->3 and ALGORITHM (+ paths).  Same topology,
#     flows, PG, seed, stop times, measurement plumbing (FLOW_TIMING_FILE is
#     inherited, giving HPCC the same FCT/BCT/CCT definitions).
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'

CELLS = [
    ('nb_b030', 'scr8_b040.txt', {'CBAP_QB2_BMAX_RATIO': '0.030'}),
    ('nb_b050', 'scr8_b040.txt', {'CBAP_QB2_BMAX_RATIO': '0.050'}),
    ('hp_s3', 'scr8_d1.txt', {'CC_MODE': '3', 'ALGORITHM': 'hpcc'}),
    ('hp_s4', 's4v_d1.txt', {'CC_MODE': '3', 'ALGORITHM': 'hpcc'}),
    ('hp_s5', 's5v_d1.txt', {'CC_MODE': '3', 'ALGORITHM': 'hpcc'}),
]


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(t):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M)
    return m.group(1) if m else None


bad = 0
for tag, src, over in CELLS:
    sp = os.path.join(B, src)
    if not os.path.isfile(sp):
        print('MISSING %s' % sp)
        sys.exit(2)
    t = load(sp)
    old = outdir_of(t)
    new = '%s_out' % tag
    t = t.replace(old + '/', new + '/').replace(old, new)
    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if not pat.search(t):
            print('%s: key %s absent in %s -- refusing to append' %
                  (tag, k, src))
            sys.exit(2)
        t = pat.sub('%s %s' % (k, v), t)
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(t)
    if not os.path.isdir(os.path.join(B, new)):
        os.makedirs(os.path.join(B, new))
    # verify: only the intended keys + paths differ from the source
    def norm(x, keys):
        out = []
        for ln in x.split('\n'):
            w = ln.split()
            if not w or w[0] in keys:
                continue
            if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
                continue
            out.append(ln.strip())
        return out
    a = norm(load(sp), set(over))
    b2 = norm(load(os.path.join(B, '%s.txt' % tag)), set(over))
    extra = [x for x in a if x not in b2] + [x for x in b2 if x not in a]
    if extra:
        bad += 1
        print('%-8s DIFFERS beyond intent: %s' % (tag, extra[:4]))
    else:
        print('wrote %-8s from %-12s  (only %s + paths)' %
              (tag, src, ','.join(sorted(over))))

print('')
hdr = '%-8s %-8s %-10s %-6s %-8s %-22s'
print(hdr % ('cell', 'CC_MODE', 'ALGO', 'STOP', 'BMAX', 'SCENARIO'))
for tag, src, over in CELLS:
    t = load(os.path.join(B, '%s.txt' % tag))

    def g(k, d='-'):
        m = re.search(r'^%s\s+(\S+)' % k, t, re.M)
        return m.group(1) if m else d
    print(hdr % (tag, g('CC_MODE'), g('ALGORITHM'),
                 g('SIMULATOR_STOP_TIME'), g('CBAP_QB2_BMAX_RATIO'),
                 g('SCENARIO')))
if bad:
    print('CONSTRUCTION FAIL')
    sys.exit(1)
print('')
print('5 cells OK')
