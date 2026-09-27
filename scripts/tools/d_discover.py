# -*- coding: utf-8 -*-
# Column discovery before writing the D1-D4 metrics extractor, so the extractor
# is written against the real schemas instead of guessed ones.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
ARMS = ['d1_dcqcn', 'd2_caponly', 'd3_capmig', 'd4_capmigband']

for a in ARMS:
    d = os.path.join(B, '%s_out' % a)
    print('=== %s  (DONE=%s) ===' % (a, os.path.isfile(os.path.join(d, 'DONE'))))
    if not os.path.isdir(d):
        print('  no dir')
        continue
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        sz = os.path.getsize(p)
        if not (f.endswith('.csv') or f == 'DONE'):
            print('  %-30s %10d' % (f, sz))
            continue
        try:
            with open(p) as fh:
                hdr = fh.readline().strip()
                n = 1 + sum(1 for _ in fh)
        except Exception as e:
            print('  %-30s <%s>' % (f, e))
            continue
        print('  %-30s %10d rows=%-7d %s' % (f, sz, max(0, n - 1), hdr[:130]))
    print('')

# the two files whose schema I must not guess
for a in ARMS:
    d = os.path.join(B, '%s_out' % a)
    for f in ('flow_timing.csv', 'selected_link_timeseries.csv',
              'flow_summary.csv'):
        p = os.path.join(d, f)
        if not os.path.isfile(p):
            continue
        rows = []
        with open(p) as fh:
            r = csv.DictReader(fh)
            for i, x in enumerate(r):
                rows.append(x)
                if i >= 2:
                    break
        print('--- %s / %s : first rows ---' % (a, f))
        for x in rows:
            print('    %s' % dict(list(x.items())[:14]))
        if f == 'flow_summary.csv':
            with open(p) as fh:
                allr = list(csv.DictReader(fh))
            comp = {}
            for x in allr:
                comp[x.get('completed')] = comp.get(x.get('completed'), 0) + 1
            print('    completed value counts: %s   total=%d' % (comp, len(allr)))
            big = [x for x in allr
                   if int(x.get('total_size_bytes', 0) or 0) >= (1 << 30)]
            print('    flows >= 1 GiB (background): %d  %s' %
                  (len(big), [(x['flow_id'], x.get('completed'),
                               x.get('acked_bytes')) for x in big[:3]]))
        print('')
    break   # one arm is enough for schema discovery
