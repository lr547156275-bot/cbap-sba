# -*- coding: utf-8 -*-
# Baseline parameter sweep on S3 (PW round).  Frozen reporting rules:
#   1. every swept point enters the frontier plot -- no post-hoc selection;
#   2. CBAP (mx_s3_cbapsba) stays fixed and is never re-tuned in response;
#   3. if some variant beats CBAP on CCT it is reported as-is and the paper
#      claim falls back to frontier dominance.
# All cells derive from the STANDARD mx_s3_<algo> configs, changing only the
# swept keys (+ output paths); the diff is verified.
# Existing points reused, not re-run: mx_s3_* (standard), sx_b_dcqcn/dctcp
# (KMIN 100/KMAX 400).
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
CELLS = [
    # DCQCN: ECN ladder + PMAX
    ('pw_dcqcn_k200', 'mx_s3_dcqcn.txt',
     {'KMIN_MAP': '1 10000000000 200', 'KMAX_MAP': '1 10000000000 800'}),
    ('pw_dcqcn_k800', 'mx_s3_dcqcn.txt',
     {'KMIN_MAP': '1 10000000000 800', 'KMAX_MAP': '1 10000000000 3200'}),
    ('pw_dcqcn_k1600', 'mx_s3_dcqcn.txt',
     {'KMIN_MAP': '1 10000000000 1600', 'KMAX_MAP': '1 10000000000 6400'}),
    ('pw_dcqcn_pmax10', 'mx_s3_dcqcn.txt',
     {'PMAX_MAP': '1 10000000000 1.0'}),
    # DCTCP: same ladder + gentler AI
    ('pw_dctcp_k200', 'mx_s3_dctcp.txt',
     {'KMIN_MAP': '1 10000000000 200', 'KMAX_MAP': '1 10000000000 800'}),
    ('pw_dctcp_k800', 'mx_s3_dctcp.txt',
     {'KMIN_MAP': '1 10000000000 800', 'KMAX_MAP': '1 10000000000 3200'}),
    ('pw_dctcp_k1600', 'mx_s3_dctcp.txt',
     {'KMIN_MAP': '1 10000000000 1600', 'KMAX_MAP': '1 10000000000 6400'}),
    ('pw_dctcp_ai500', 'mx_s3_dctcp.txt',
     {'DCTCP_RATE_AI': '500Mb/s'}),
    # HPCC: eta + MI
    ('pw_hpcc_u90', 'mx_s3_hpcc.txt', {'U_TARGET': '0.90'}),
    ('pw_hpcc_u98', 'mx_s3_hpcc.txt', {'U_TARGET': '0.98'}),
    ('pw_hpcc_mi1', 'mx_s3_hpcc.txt', {'MI_THRESH': '1'}),
    # TIMELY: RATE_AI only (its T_LOW/T_HIGH are not exposed by the harness
    # config parser -- disclosed limitation, option ii by decision)
    ('pw_timely_ai25', 'mx_s3_timely.txt', {'RATE_AI': '25Mb/s'}),
    ('pw_timely_ai100', 'mx_s3_timely.txt', {'RATE_AI': '100Mb/s'}),
    ('pw_timely_ai200', 'mx_s3_timely.txt', {'RATE_AI': '200Mb/s'}),
]


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


bad = 0
for tag, src, over in CELLS:
    sp = os.path.join(B, src)
    t = load(sp)
    old = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M).group(1)
    new = '%s_out' % tag
    t = t.replace(old + '/', new + '/').replace(old, new)
    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if not pat.search(t):
            print('%s: key %s absent' % (tag, k))
            sys.exit(2)
        t = pat.sub('%s %s' % (k, v), t)
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(t)
    if not os.path.isdir(os.path.join(B, new)):
        os.makedirs(os.path.join(B, new))

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
        print('%s DIFFERS beyond intent: %s' % (tag, extra[:3]))
    else:
        print('wrote %-18s = %s + %s' % (tag, src.replace('.txt', ''),
                                         ','.join(sorted(over))))
if bad:
    sys.exit(1)
print('')
print('14 sweep cells OK (CBAP untouched; standard + sx_b points reused)')
