# -*- coding: utf-8 -*-
# Sensitivity annex extraction.  Each variant cell is compared against its
# STANDARD-config main-matrix twin (mx_s3_<algo>).  Tables carry the
# ENV_SENSITIVITY / ECN_SENSITIVITY label and never merge into the matrix.
# Pre-registered expectations (from the 2026-08-21 approval):
#   A (BUFFER 8->2 MB): baselines hit PFC/drops; CBAP ~unchanged.
#   B (KMIN 100/KMAX 400): baselines trade completion for queue; CBAP
#     ~unchanged (its queues sit below either threshold).
# Whatever the data says is what gets reported.
import csv
import os

B = '/work/simulation/experiment/scheme1_sba'
BG_MIN = 1 << 30
Q_ABS = 1048575.0


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


def arm(tag, logdir):
    d = os.path.join(B, '%s_out' % tag)
    o = dict(arm=tag)
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
    o['expected'] = len([r for r in fs
                         if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN])
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
    log = '%s/%s.log' % (logdir, tag)
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['drops'] = dr
    return o


def table(title, pairs):
    print('')
    print('=== %s ===' % title)
    hdr = ('%-10s %-9s %6s %10s %9s %8s %10s %10s %6s %5s %5s %5s')
    print(hdr % ('algo', 'variant', 'done', 'CCT_ms', 'FCTp99', 'goodput',
                 'q_p99', 'q_max', 'ovQabs', 'PFC', 'drop', 'retx'))
    for algo, var_tag in pairs:
        base = arm('mx_s3_%s' % algo, '/work/mx_logs')
        var = arm(var_tag, '/work/sens_logs')
        for lab, o in (('standard', base), ('variant', var)):
            if o.get('status') != 'OK':
                print(hdr % (algo, lab, o.get('status'), '-', '-', '-', '-',
                             '-', '-', '-', '-', '-'))
                continue
            print(hdr % (algo, lab, '%d/%d' % (o['done'], o['expected']),
                         '%.4f' % o['CCT_ms'],
                         '%.3f' % o['FCT_p99_ms'],
                         '%.4f' % o['goodput_G'],
                         '%.0f' % o['q_p99_B'], '%.0f' % o['q_max_B'],
                         '%d' % o['over_qabs'], '%d' % o['pfc'],
                         '%d' % o['drops'], '%d' % o['retx']))
        if base.get('CCT_ms') and var.get('CCT_ms'):
            print('%-10s   delta: CCT %+.2f%%  q_max %+.1fx  PFC %d->%d '
                  'retx %d->%d'
                  % (algo,
                     (var['CCT_ms'] - base['CCT_ms']) / base['CCT_ms'] * 100,
                     (var['q_max_B'] / base['q_max_B']) if base['q_max_B']
                     else 0, base['pfc'], var['pfc'], base['retx'],
                     var['retx']))


table('Group A -- ENV_SENSITIVITY (BUFFER_SIZE 8 -> 2 MB, uniform, S3)',
      [(a, 'sx_a_%s' % a) for a in
       ('dcqcn', 'dctcp', 'timely', 'hpcc', 'cbapsba')])
table('Group B -- ECN_SENSITIVITY (KMIN 400->100, KMAX 1600->400, S3)',
      [(a, 'sx_b_%s' % a) for a in ('dcqcn', 'dctcp', 'cbapsba')])
print('')
print('Annex tables only; the main matrix (standard config) is unchanged.')
