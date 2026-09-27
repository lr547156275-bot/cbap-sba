# -*- coding: utf-8 -*-
# Extract the re-measured H_eff at 400G (p99 of first_affected_at_bottleneck,
# rounded up to a whole us) and write it to reports/HG400_US for the config
# generator.  Substitution rule pre-declared in the overnight plan.
import math
import os
import sys

P = '/work/v2_400g/results/heff_400g/actuation.csv'
OUT = '/work/v2_400g/reports/HG400_US'
if not os.path.isfile(P) or os.path.getsize(P) == 0:
    print('HG_EXTRACT_FAIL: actuation.csv missing/empty')
    sys.exit(2)
v = []
hdr = None
for ln in open(P):
    w = ln.rstrip('\n').split(',')
    if hdr is None:
        hdr = {k: i for i, k in enumerate(w)}
        continue
    try:
        if w[hdr['stage']] == 'first_affected_at_bottleneck':
            v.append(float(w[hdr['delta_from_command_ns']]))
    except (ValueError, IndexError, KeyError):
        continue
if len(v) < 100:
    print('HG_EXTRACT_FAIL: only %d samples' % len(v))
    sys.exit(2)
v.sort()
p99 = v[int(round((len(v) - 1) * 0.99))]
hg = math.ceil(p99 / 1000.0)
open(OUT, 'w').write('%d\n' % hg)
print('H_eff@400G re-measured (bg alive): n=%d p99=%.2fus -> H_GUARD=%dus '
      '(written to %s)' % (len(v), p99 / 1e3, hg, OUT))
