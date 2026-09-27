# -*- coding: utf-8 -*-
# Complete item 1: extend the rate_transition.csv writer in third.cc.
# rdma-hw.{h,cc} were already patched; only this file remained, because my
# previous anchor assumed capacityValid and the newline were on one source line
# when they are on two.
import io
import sys

T = '/work/simulation/scratch/third.cc'
t = io.open(T, encoding='utf-8', errors='surrogateescape').read()

if 'actuation_kind' in t:
    print('already applied')
    sys.exit(0)

hdr = 'stale_feedback,capacity_valid\\n";'
if t.count(hdr) != 1:
    print('ANCHOR FAIL [hdr]: %d' % t.count(hdr))
    sys.exit(2)

row = ("<< r.rebalanceEndNs << ',' << r.staleFeedback << ',' << r.capacityValid\n"
       "\t\t\t\t<< '\\n';")
if t.count(row) != 1:
    print('ANCHOR FAIL [row]: %d' % t.count(row))
    for i, ln in enumerate(t.split('\n'), 1):
        if 'capacityValid' in ln:
            print('  %d: %r' % (i, ln))
    sys.exit(2)

t = t.replace(hdr,
              'stale_feedback,capacity_valid,"\n'
              '\t\t\t"role,owner_before,owner_after,side,actuation_kind,"\n'
              '\t\t\t"applied_rate_after_bps\\n";', 1)

t = t.replace(row,
              "<< r.rebalanceEndNs << ',' << r.staleFeedback << ',' << r.capacityValid\n"
              "\t\t\t\t<< ',' << r.role << ',' << r.ownerBefore\n"
              "\t\t\t\t<< ',' << r.ownerAfter << ',' << r.side\n"
              "\t\t\t\t<< ',' << r.actuationKind\n"
              "\t\t\t\t<< ',' << r.appliedRateAfterBps\n"
              "\t\t\t\t<< '\\n';", 1)

io.open(T, 'w', encoding='utf-8', errors='surrogateescape').write(t)
print('third.cc writer extended')
print('  header cols : %d' % t.count('actuation_kind'))
print('  row fields  : %d' % t.count('r.appliedRateAfterBps'))
