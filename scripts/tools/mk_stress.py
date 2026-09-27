# -*- coding: utf-8 -*-
# Stress cells (item 5): batch-overlap injection, three probe points.
#
# Mechanism (pre-registered): during A/B overlap the MIN_RATE floor sum is
# structurally infeasible (129 flows x 104.8M wire ~= 13.5G > C = 10G), so the
# queue MUST grow at (sum_floor - C)/8 ~= 437 KB/ms until batch A completes;
# floors then become feasible and the controller drains back to GREEN.  This
# legally exercises GREEN->HOLD->DRAIN(->RED)->GREEN without touching Q_abs,
# checkers, MAX_BOOST or any frozen boundary -- only NEW scenario files.
#
# Probes (A completes deterministically at 2.056995 s under scr8_b040):
#   st_2560  B released 2.0560 s  -> expect HOLD round-trip (~550 KB peak)
#   st_2555  B released 2.0555 s  -> expect DRAIN engagement (~800 KB peak)
#   st_2550  B released 2.0550 s  -> RED boundary probe; a transient Q_abs
#            excursion here documents the infeasible-floor structural limit
#            and is recorded as such, NOT hidden and NOT a candidate gate.
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
NA = 64                  # batch A flows (same as S3)
NB = 64                  # batch B flows (same hosts, port 101)
PROBES = [('st_2560', 2056000000), ('st_2555', 2055500000),
          ('st_2550', 2055000000)]

# ---- shared flow/path files (release time lives in the schedule) ----------
nflow = 1 + NA + NB
flow = ['%d' % nflow, '65 64 3 100 4000000000 0.5']
for s in range(NA):
    flow.append('%d 64 3 100 1048576 1.9' % s)
for s in range(NB):
    flow.append('%d 64 3 101 1048576 1.9' % s)
io.open(os.path.join(B, 'st_flow.txt'), 'w').write('\n'.join(flow) + '\n')

path = ['%d' % nflow]
for i in range(nflow):
    path.append('%d 1 0' % i)
io.open(os.path.join(B, 'st_cbap_path.txt'), 'w').write('\n'.join(path) + '\n')
print('wrote st_flow.txt (%d flows: bg + %dxA@port100 + %dxB@port101)'
      % (nflow, NA, NB))
print('wrote st_cbap_path.txt (all on link 0, same bottleneck)')

# ---- per-probe schedule + config ------------------------------------------
src = os.path.join(B, 'scr8_b040.txt')
base = io.open(src, encoding='utf-8', errors='surrogateescape').read()
m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', base, re.M)
oldout = m.group(1)

for tag, relB in PROBES:
    sch = ['%d' % nflow, '0 0 0 1 4000000000 0 0 0 1000000000']
    for i in range(NA):
        sch.append('%d 0 1 %d 1048576 0 0 0 2000000000' % (1 + i, NA))
    for i in range(NB):
        sch.append('%d 0 2 %d 1048576 0 0 0 %d' % (1 + NA + i, NB, relB))
    io.open(os.path.join(B, '%s_round_schedule.txt' % tag), 'w') \
        .write('\n'.join(sch) + '\n')

    t = base.replace(oldout + '/', '%s_out/' % tag).replace(oldout,
                                                            '%s_out' % tag)
    for k, v in (('FLOW_FILE', 'st_flow.txt'),
                 ('ROUND_SCHEDULE_FILE', '%s_round_schedule.txt' % tag),
                 ('CBAP_PATH_FILE', 'st_cbap_path.txt'),
                 ('SCENARIO', '%s_overlap_stress' % tag)):
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if not pat.search(t):
            print('key %s missing in source -- abort' % k)
            sys.exit(2)
        t = pat.sub('%s %s' % (k, v), t)
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(t)
    d = os.path.join(B, '%s_out' % tag)
    if not os.path.isdir(d):
        os.makedirs(d)
    print('wrote %s.txt  (B release %.4f s)' % (tag, relB / 1e9))

# ---- verify: configs differ from scr8_b040 ONLY in the 4 scenario keys ----
KEYS = {'FLOW_FILE', 'ROUND_SCHEDULE_FILE', 'CBAP_PATH_FILE', 'SCENARIO'}


def norm(txt):
    out = []
    for ln in txt.split('\n'):
        w = ln.split()
        if not w or w[0] in KEYS:
            continue
        if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
            continue
        out.append(ln.strip())
    return out


bad = 0
a = norm(base)
for tag, _ in PROBES:
    b2 = norm(io.open(os.path.join(B, '%s.txt' % tag),
                      encoding='utf-8', errors='surrogateescape').read())
    extra = [x for x in a if x not in b2] + [x for x in b2 if x not in a]
    if extra:
        bad += 1
        print('%s DIFFERS beyond scenario keys: %s' % (tag, extra[:4]))
    else:
        print('%s clean: b040 config + new scenario files only' % tag)

# floor arithmetic printed so the pre-registration is checkable
wire = 104.8576e6
print('')
print('floor sum during overlap : %.3f G (%d flows) vs C=10G -> structurally'
      ' infeasible, growth ~%.0f KB/ms'
      % (nflow * wire / 1e9, nflow, (nflow * wire - 10e9) / 8 / 1e3 / 1e3 * 1e3))
print('floor sum after A done   : %.3f G (%d flows) -> feasible, drain right'
      ' = %.2f G' % ((1 + NB) * wire / 1e9, 1 + NB,
                     (10e9 - (1 + NB) * wire) / 1e9))
if bad:
    sys.exit(1)
print('3 stress cells OK')
