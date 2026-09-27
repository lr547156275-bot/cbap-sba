# -*- coding: utf-8 -*-
# PW round: baseline parameter frontier vs the FIXED CBAP point (S3).
# Emits: per-point table, per-algorithm best-CCT / best-queue comparisons,
# frontier-dominance verdict, and figdata/frontier_s3.csv for the scatter.
# Rule 3 honoured: any variant beating CBAP on any axis is printed as-is.
import csv
import os

B = '/work/simulation/experiment/scheme1_sba'
BG_MIN = 1 << 30
Q_ABS = 1048575.0

POINTS = [
    # (algo, label, cell, logdir)
    ('dcqcn', 'k100', 'sx_b_dcqcn', '/work/sens_logs'),
    ('dcqcn', 'k200', 'pw_dcqcn_k200', '/work/pw_logs'),
    ('dcqcn', 'std_k400', 'mx_s3_dcqcn', '/work/mx_logs'),
    ('dcqcn', 'k800', 'pw_dcqcn_k800', '/work/pw_logs'),
    ('dcqcn', 'k1600', 'pw_dcqcn_k1600', '/work/pw_logs'),
    ('dcqcn', 'pmax1.0', 'pw_dcqcn_pmax10', '/work/pw_logs'),
    ('dctcp', 'k100', 'sx_b_dctcp', '/work/sens_logs'),
    ('dctcp', 'k200', 'pw_dctcp_k200', '/work/pw_logs'),
    ('dctcp', 'std_k400', 'mx_s3_dctcp', '/work/mx_logs'),
    ('dctcp', 'k800', 'pw_dctcp_k800', '/work/pw_logs'),
    ('dctcp', 'k1600', 'pw_dctcp_k1600', '/work/pw_logs'),
    ('dctcp', 'ai500', 'pw_dctcp_ai500', '/work/pw_logs'),
    ('timely', 'ai25', 'pw_timely_ai25', '/work/pw_logs'),
    ('timely', 'std_ai50', 'mx_s3_timely', '/work/mx_logs'),
    ('timely', 'ai100', 'pw_timely_ai100', '/work/pw_logs'),
    ('timely', 'ai200', 'pw_timely_ai200', '/work/pw_logs'),
    ('hpcc', 'u0.90', 'pw_hpcc_u90', '/work/pw_logs'),
    ('hpcc', 'std_u0.95', 'mx_s3_hpcc', '/work/mx_logs'),
    ('hpcc', 'u0.98', 'pw_hpcc_u98', '/work/pw_logs'),
    ('hpcc', 'mi1', 'pw_hpcc_mi1', '/work/pw_logs'),
    ('cbapsba', 'b040_fixed', 'mx_s3_cbapsba', '/work/mx_logs'),
]


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


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[int(round((len(s) - 1) * q))]


def arm(cell, logdir):
    d = os.path.join(B, '%s_out' % cell)
    o = dict(cell=cell)
    if not os.path.isfile(os.path.join(d, 'DONE')):
        o['status'] = 'NOT_DONE'
        return o
    o['status'] = 'OK'
    ft = rd(os.path.join(d, 'flow_timing.csv'))
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    ts = rd(os.path.join(d, 'selected_link_timeseries.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
    inc = [r for r in ft if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN]
    fcts, lastack, ready, release = [], [], [], []
    for r in inc:
        a, t0 = f(r, 'last_ack_ns'), f(r, 'first_data_tx_ns')
        if a is None or not t0:
            continue
        fcts.append((a - t0) / 1e6)
        lastack.append(a)
        v = f(r, 'application_ready_ns')
        if v:
            ready.append(v)
        v = f(r, 'network_release_ns')
        if v:
            release.append(v)
    o['done'] = len(fcts)
    lastNs = max(lastack) if lastack else None
    ref = (min(ready) if ready else None) or \
        (min(release) if release else None)
    o['CCT_ms'] = ((lastNs - ref) / 1e6) if (lastNs and ref) else None
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['goodput_G'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    q = [f(r, 'queue_bytes') for r in ts]
    q = [x for x in q if x is not None]
    if q:
        o['q_p99_B'] = pct(q, 0.99)
        o['q_max_B'] = max(q)
        o['over_qabs'] = sum(1 for x in q if x > Q_ABS)
    o['pfc'] = len(pf)
    o['retx'] = sum(int(float(r.get('retx_events', 0) or 0)) for r in fs)
    log = '%s/%s.log' % (logdir, cell)
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['drops'] = dr
    return o


rows = []
for algo, label, cell, logdir in POINTS:
    o = arm(cell, logdir)
    o['algo'] = algo
    o['label'] = label
    rows.append(o)

hdr = '%-8s %-10s %-8s %10s %9s %8s %10s %10s %6s %5s %5s'
print(hdr % ('algo', 'variant', 'status', 'CCT_ms', 'FCTp99', 'goodput',
             'q_p99', 'q_max', 'ovQabs', 'PFC', 'retx'))
for o in rows:
    if o.get('status') != 'OK':
        print(hdr % (o['algo'], o['label'], o['status'], '-', '-', '-', '-',
                     '-', '-', '-', '-'))
        continue
    print(hdr % (o['algo'], o['label'], '%d/64' % o['done'],
                 '%.4f' % o['CCT_ms'], '%.3f' % o['FCT_p99_ms'],
                 '%.4f' % o['goodput_G'], '%.0f' % o['q_p99_B'],
                 '%.0f' % o['q_max_B'], '%d' % o['over_qabs'],
                 '%d' % o['pfc'], '%d' % o['retx']))

cbap = [o for o in rows if o['algo'] == 'cbapsba'][0]
print('')
print('=== per-algorithm best points vs fixed CBAP '
      '(CCT %.4f ms, q_p99 %.0f B) ===' % (cbap['CCT_ms'], cbap['q_p99_B']))
dominated = True
for algo in ('dcqcn', 'dctcp', 'timely', 'hpcc'):
    pts = [o for o in rows if o['algo'] == algo and o.get('status') == 'OK']
    if not pts:
        continue
    bc = min(pts, key=lambda o: o['CCT_ms'])
    bq = min(pts, key=lambda o: o['q_p99_B'])
    print('%-7s best-CCT  %-9s CCT %+.2f%% vs CBAP, q_p99 %5.1fx CBAP'
          % (algo, bc['label'], (bc['CCT_ms'] - cbap['CCT_ms']) /
             cbap['CCT_ms'] * 100, bc['q_p99_B'] / cbap['q_p99_B']))
    print('%-7s best-q    %-9s CCT %+.2f%% vs CBAP, q_p99 %5.1fx CBAP'
          % (algo, bq['label'], (bq['CCT_ms'] - cbap['CCT_ms']) /
             cbap['CCT_ms'] * 100, bq['q_p99_B'] / cbap['q_p99_B']))
    for o in pts:
        if o['CCT_ms'] <= cbap['CCT_ms'] and o['q_p99_B'] <= cbap['q_p99_B']:
            dominated = False
            print('  !! %s/%s enters CBAP region (CCT %.4f, q_p99 %.0f) -- '
                  'dominance falls, reported as-is' %
                  (algo, o['label'], o['CCT_ms'], o['q_p99_B']))
print('')
print('FRONTIER VERDICT: %s' %
      ('FRONTIER_DOMINANCE_HOLDS -- no swept baseline point matches CBAP on '
       'both axes' if dominated else 'DOMINANCE_BROKEN -- see !! lines'))

fig = os.path.join(B, 'figdata')
if not os.path.isdir(fig):
    os.makedirs(fig)
with open(os.path.join(fig, 'frontier_s3.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['algo', 'variant', 'CCT_ms', 'FCT_p99_ms', 'goodput_G',
                'q_p99_B', 'q_max_B', 'over_qabs', 'pfc', 'retx'])
    for o in rows:
        if o.get('status') == 'OK':
            w.writerow([o['algo'], o['label'], o['CCT_ms'], o['FCT_p99_ms'],
                        o['goodput_G'], o['q_p99_B'], o['q_max_B'],
                        o['over_qabs'], o['pfc'], o['retx']])
print('wrote figdata/frontier_s3.csv (%d points)' %
      len([o for o in rows if o.get('status') == 'OK']))
