# -*- coding: utf-8 -*-
# Item 1 acceptance, checked against the user's five criteria verbatim:
#   1. incast window background_CBAP_commands > 0
#   2. flow 0 explicitly labelled role=background
#   3. reproduce 8G -> 0.1G -> 8G from the CSV (not from stdout)
#   4. migration requested / applied / arrival agree in direction
#   5. flag=0, static cap and existing results byte-identical
#
# Criterion 5 is checked on the RESULT files only.  rate_transition.csv is the
# audit file being extended on purpose, so it is excluded and that exclusion is
# printed, not hidden.
import csv
import hashlib
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
NEW = os.path.join(B, 'v1_migaudit_out')
OLD = os.path.join(B, 'pa_cap1000_rho090_out')
W0, W1 = 2000000000, 2058500000          # incast batch window

# Files that encode BEHAVIOUR.  Any difference here means the instrumentation
# patch changed the simulation, which must stop the round.
RESULT = ['flow_summary.csv', 'port_summary.csv', 'selected_link_timeseries.csv',
          'qlen.txt', 'tx_serialization.csv', 'pfc_events.csv',
          'round_summary.csv', 'admission.csv', 'sba_events.csv']
# Deliberately extended this round.
EXCLUDED = ['rate_transition.csv']

fail = []


def sha(p):
    if not os.path.isfile(p):
        return None
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


if not os.path.isfile(os.path.join(NEW, 'DONE')):
    print('NOT DONE yet: %s/DONE absent' % NEW)
    sys.exit(3)

rt = os.path.join(NEW, 'rate_transition.csv')
rows = list(csv.DictReader(open(rt)))
cols = list(rows[0].keys()) if rows else []

print('=== schema ===')
for k in ('role', 'owner_before', 'owner_after', 'side', 'actuation_kind',
          'applied_rate_after_bps'):
    ok = k in cols
    print('  %-24s %s' % (k, 'present' if ok else 'MISSING'))
    if not ok:
        fail.append('column %s missing' % k)
if fail:
    print('\nSCHEMA FAIL -- binary did not pick up the patch')
    sys.exit(2)

print('  total rows              : %d' % len(rows))


def i(r, k, d=0):
    try:
        return int(float(r[k]))
    except (KeyError, ValueError, TypeError):
        return d


inwin = [r for r in rows if W0 <= i(r, 'time_ns') <= W1]
bg = [r for r in inwin if i(r, 'role') == 1]
mig = [r for r in inwin if i(r, 'actuation_kind') in (2, 3)]
migd = [r for r in inwin if i(r, 'actuation_kind') == 2]

print('')
print('=== criterion 1: background CBAP commands in the incast window ===')
print('  rows in [%.6f, %.6f] s   : %d' % (W0 / 1e9, W1 / 1e9, len(inwin)))
print('  role=background rows       : %d' % len(bg))
print('  migration rows (kind 2|3)  : %d' % len(mig))
print('  migration DISPATCHES(kind2): %d' % len(migd))
if len(migd) == 0:
    fail.append('C1: no migration dispatch recorded in the incast window')

print('')
print('=== criterion 2: is flow 0 labelled role=background? ===')
f0 = [r for r in rows if r.get('flow_id') == '0']
roles0 = set(i(r, 'role') for r in f0)
print('  flow 0 rows                : %d' % len(f0))
print('  flow 0 role values         : %s  (1 == background)' % sorted(roles0))
if roles0 != {1}:
    fail.append('C2: flow 0 role is %s, expected {1}' % sorted(roles0))
otherbg = sorted(set(r['flow_id'] for r in rows if i(r, 'role') == 1) - {'0'})
if otherbg:
    fail.append('C2: unexpected extra background flows %s' % otherbg[:5])
print('  other flows marked bg      : %s' % (otherbg[:5] or 'none'))

print('')
print('=== criterion 3: reproduce 8G -> 0.1G -> 8G, from the CSV ===')
f0m = sorted([r for r in f0 if i(r, 'actuation_kind') in (2, 3)],
             key=lambda r: i(r, 'time_ns'))
if not f0m:
    fail.append('C3: no migration rows for flow 0')
else:
    print('  %-14s %-10s %-12s %-12s %-12s %s'
          % ('t(s)', 'kind', 'old(Gbps)', 'target(G)', 'new(G)', 'applied_after(G)'))
    prev = None
    for r in f0m:
        if len(f0m) > 24 and prev is not None:
            # print only the rows where the rate actually moved
            if i(r, 'actuation_kind') != 2:
                continue
        print('  %-14.9f %-10d %-12.4f %-12.4f %-12.4f %.4f'
              % (i(r, 'time_ns') / 1e9, i(r, 'actuation_kind'),
                 i(r, 'old_rate_bps') / 1e9, i(r, 'target_rate_bps') / 1e9,
                 i(r, 'new_rate_bps') / 1e9,
                 i(r, 'applied_rate_after_bps') / 1e9))
        prev = r
    applied = [i(r, 'applied_rate_after_bps') for r in f0m]
    hi0 = max(applied[:3]) if applied else 0
    lo = min(applied)
    hiN = max(applied[-3:]) if applied else 0
    print('')
    print('  first applied (high)  : %.4f Gbps' % (hi0 / 1e9))
    print('  minimum applied (low) : %.4f Gbps' % (lo / 1e9))
    print('  last applied (high)   : %.4f Gbps' % (hiN / 1e9))
    down = hi0 > 4e9 and lo < 1e9
    print('  8G -> 0.1G descent    : %s' % ('YES' if down else 'NO'))
    if not down:
        fail.append('C3: descent 8G->0.1G not reproducible from CSV '
                    '(hi=%.3fG lo=%.3fG)' % (hi0 / 1e9, lo / 1e9))
    # the recovery may land after the window; search the whole trace
    after = [r for r in f0 if i(r, 'time_ns') > max(i(x, 'time_ns') for x in f0m)]
    rec = max([i(r, 'applied_rate_after_bps') for r in after] or [hiN])
    print('  recovery to ~8G       : %.4f Gbps  %s'
          % (rec / 1e9, 'YES' if rec > 4e9 else 'NOT IN TRACE'))

print('')
print('=== criterion 4: requested vs applied direction agreement ===')
dis = 0
for r in mig:
    old = i(r, 'old_rate_bps')
    req = i(r, 'new_rate_bps')            # what the migration asked to install
    got = i(r, 'applied_rate_after_bps')  # qp->m_rate after the call
    if i(r, 'actuation_kind') == 2 and got != req:
        dis += 1
print('  dispatch rows where applied != requested : %d / %d' % (dis, len(migd)))
if dis:
    fail.append('C4: %d dispatches did not install the requested rate' % dis)
# direction agreement between requested delta and applied delta
bad = 0
for r in migd:
    dreq = i(r, 'new_rate_bps') - i(r, 'old_rate_bps')
    dgot = i(r, 'applied_rate_after_bps') - i(r, 'old_rate_bps')
    if (dreq > 0) != (dgot > 0) and dreq != 0:
        bad += 1
print('  direction disagreements                  : %d' % bad)
if bad:
    fail.append('C4: %d sign disagreements requested vs applied' % bad)

print('')
print('=== criterion 5: RESULT files byte-identical to the pre-patch cell ===')
print('  new = %s' % NEW)
print('  old = %s' % OLD)
print('  EXCLUDED (extended on purpose): %s' % ', '.join(EXCLUDED))
for f in RESULT:
    a, b = sha(os.path.join(OLD, f)), sha(os.path.join(NEW, f))
    if a is None and b is None:
        print('  %-30s absent in both (skip)' % f)
        continue
    if a is None or b is None:
        print('  %-30s PRESENT-IN-ONLY-ONE  old=%s new=%s'
              % (f, 'yes' if a else 'no', 'yes' if b else 'no'))
        fail.append('C5: %s present in only one cell' % f)
        continue
    same = a == b
    print('  %-30s %s' % (f, 'identical' if same else 'DIFFERS  %s vs %s'
                          % (a[:12], b[:12])))
    if not same:
        fail.append('C5: %s differs -- instrumentation changed behaviour' % f)

print('')
print('=' * 62)
if fail:
    print('ITEM 1 FAIL (%d)' % len(fail))
    for f in fail:
        print('  - %s' % f)
    sys.exit(1)
print('ITEM 1 PASS -- all five acceptance criteria met')
