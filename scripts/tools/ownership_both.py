# -*- coding: utf-8 -*-
# per_flow_control_ownership.csv, rebuilt from BOTH actuation paths.
#
# The previous version read only the SetCbapRate() path and therefore reported
# 0 background commands, which is what led me to the wrong conclusion that CBAP
# does not migrate the background flow.  Since item 1 both paths land in
# rate_transition.csv, distinguished by actuation_kind:
#     0 setrate dispatch   1 setrate no-op
#     2 migration dispatch 3 migration no-op
# so a per-flow census now covers the whole controller, and replan volume can no
# longer be mistaken for command volume.
#
# The old file's verdict text ("old-to-new capacity migration is NOT supported")
# is deleted, not softened: it was refuted by the migration trace.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
BG_MIN = 1 << 30
W0, W1 = 2000000000, 2058500000


def rd(p):
    if not os.path.isfile(p):
        return []
    with open(p) as fh:
        return list(csv.DictReader(fh))


def f(r, k, d=None):
    try:
        return float(r[k])
    except (KeyError, ValueError, TypeError):
        return d


def cfg(p, k, d=None):
    if not os.path.isfile(p):
        return d
    with open(p) as fh:
        for ln in fh:
            w = ln.split()
            if len(w) >= 2 and w[0] == k:
                return w[1]
    return d


cells = sys.argv[1:] or ['d2_caponly', 'd3_capmig', 'd4_capmigband']
ALL = []
for tag in cells:
    d = os.path.join(B, '%s_out' % tag)
    conf = os.path.join(B, '%s.txt' % tag)
    if not os.path.isfile(os.path.join(d, 'DONE')):
        print('%-16s NOT DONE, skipped' % tag)
        continue
    rt = rd(os.path.join(d, 'rate_transition.csv'))
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    ft = rd(os.path.join(d, 'flow_timing.csv'))
    if not rt:
        print('%-16s no rate_transition.csv' % tag)
        continue
    if 'actuation_kind' not in rt[0]:
        print('%-16s rate_transition.csv predates item 1 (no actuation_kind); '
              'cannot attribute both paths' % tag)
        continue

    size = {}
    for r in fs:
        size[r.get('flow_id')] = f(r, 'total_size_bytes', 0) or 0
    for r in ft:
        size.setdefault(r.get('flow_id'), f(r, 'total_size_bytes', 0) or 0)

    per = {}
    for r in rt:
        fid = r.get('flow_id')
        t = f(r, 'time_ns', 0) or 0
        try:
            k = int(float(r['actuation_kind']))
        except (KeyError, ValueError, TypeError):
            k = -1
        p = per.setdefault(fid, dict(
            flow_id=fid, cell=tag,
            role='background' if (int(float(r['role'])) if r.get('role') not in (None, '') else 0) == 1 else 'incast',
            setrate_dispatch=0, setrate_noop=0,
            migration_dispatch=0, migration_noop=0,
            setrate_dispatch_win=0, migration_dispatch_win=0,
            owner_before_cbap=0, owner_before_dcqcn=0,
            owner_after_cbap=0, owner_after_dcqcn=0,
            side_new=0, side_old=0, side_none=0,
            first_cmd_s=None, last_cmd_s=None,
            applied_min_Gbps=None, applied_max_Gbps=None))
        key = {0: 'setrate_dispatch', 1: 'setrate_noop',
               2: 'migration_dispatch', 3: 'migration_noop'}.get(k)
        if key:
            p[key] += 1
        if W0 <= t <= W1:
            if k == 0:
                p['setrate_dispatch_win'] += 1
            if k == 2:
                p['migration_dispatch_win'] += 1
        ob = (int(float(r['owner_before'])) if r.get('owner_before') not in (None, '') else 0)
        oa = (int(float(r['owner_after'])) if r.get('owner_after') not in (None, '') else 0)
        p['owner_before_dcqcn' if ob else 'owner_before_cbap'] += 1
        p['owner_after_dcqcn' if oa else 'owner_after_cbap'] += 1
        sd = (int(float(r['side'])) if r.get('side') not in (None, '') else 2)
        p['side_new' if sd == 0 else ('side_old' if sd == 1 else 'side_none')] += 1
        ts = t / 1e9
        if p['first_cmd_s'] is None or ts < p['first_cmd_s']:
            p['first_cmd_s'] = ts
        if p['last_cmd_s'] is None or ts > p['last_cmd_s']:
            p['last_cmd_s'] = ts
        ar = f(r, 'applied_rate_after_bps')
        if ar is not None:
            g = ar / 1e9
            if p['applied_min_Gbps'] is None or g < p['applied_min_Gbps']:
                p['applied_min_Gbps'] = g
            if p['applied_max_Gbps'] is None or g > p['applied_max_Gbps']:
                p['applied_max_Gbps'] = g

    for fid, p in per.items():
        sz = size.get(fid)
        if sz:
            p['size_bytes'] = sz
            # cross-check the role label against the actual flow size
            expect = 'background' if sz >= BG_MIN else 'incast'
            p['role_matches_size'] = int(expect == p['role'])
        else:
            p['size_bytes'] = None
            p['role_matches_size'] = None
        p['total_dispatch'] = p['setrate_dispatch'] + p['migration_dispatch']
        p['total_noop'] = p['setrate_noop'] + p['migration_noop']
        p['migration_enabled_cfg'] = cfg(conf, 'CBAP_MIGRATION_ENABLE', '-')
        p['queue_band_cfg'] = cfg(conf, 'CBAP_QUEUE_BAND_ENABLE', '-')
        ALL.append(p)

if not ALL:
    print('nothing to write')
    sys.exit(3)

out = os.path.join(B, 'per_flow_control_ownership.csv')
keys = []
for r in ALL:
    for k in r:
        if k not in keys:
            keys.append(k)
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    for r in sorted(ALL, key=lambda x: (x['cell'], int(x['flow_id'] or 0))):
        w.writerow(r)
print('wrote %s  (%d flow-rows, %d cells, BOTH actuation paths)'
      % (out, len(ALL), len(set(r['cell'] for r in ALL))))

mism = [r for r in ALL if r['role_matches_size'] == 0]
print('role/size mismatches: %d %s' % (len(mism),
                                       [(r['cell'], r['flow_id']) for r in mism[:5]]))

print('')
print('=== background flow, per cell: both paths ===')
h = '%-16s %-8s %10s %10s %10s %10s %9s %9s'
print(h % ('cell', 'flow', 'setrate', 'migration', 'set_win', 'mig_win',
           'min_G', 'max_G'))
for r in sorted(ALL, key=lambda x: x['cell']):
    if r['role'] != 'background':
        continue
    print(h % (r['cell'], r['flow_id'], r['setrate_dispatch'],
               r['migration_dispatch'], r['setrate_dispatch_win'],
               r['migration_dispatch_win'],
               '%.4f' % (r['applied_min_Gbps'] or 0),
               '%.4f' % (r['applied_max_Gbps'] or 0)))

print('')
print('=== per-cell actuation totals (incast vs background) ===')
h2 = '%-16s %-11s %8s %10s %10s %10s'
print(h2 % ('cell', 'role', 'flows', 'dispatch', 'migration', 'noop'))
for cell in sorted(set(r['cell'] for r in ALL)):
    for role in ('incast', 'background'):
        g = [r for r in ALL if r['cell'] == cell and r['role'] == role]
        if not g:
            continue
        print(h2 % (cell, role, len(g),
                    sum(r['setrate_dispatch'] for r in g),
                    sum(r['migration_dispatch'] for r in g),
                    sum(r['total_noop'] for r in g)))
