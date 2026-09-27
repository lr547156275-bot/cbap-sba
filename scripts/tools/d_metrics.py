# -*- coding: utf-8 -*-
# D1-D4 unified metrics extractor.
#
# FROZEN DEFINITIONS (item 3):
#   per-flow FCT_i = last_ack_ns_i - first_data_tx_ns_i
#   BCT            = max_i(last_ack_ns) - network_release_ns
#   CCT            = max_i(last_ack_ns) - application_ready_ns
#   injection_end_time is reported separately and is NEVER called BCT.
#
# COMPARABILITY, stated rather than buried:
#   CBAP has two batch reference points (application_ready 2.000000000 s and
#   network_release 2.000005000 s); DCQCN has no admission stage and only one
#   (the flow start, 2.0 s).  So CCT is the cross-algorithm metric.  Comparing
#   CBAP's BCT against a baseline measured from 2.0 s would hand CBAP the 5.0 us
#   admission delay for free.  Both are emitted; only CCT is marked comparable.
#
# KNOWN LIMITATION, not a silent gap:
#   flow_timing.csv is written in the flow-completion handler, so the 4 GiB
#   background flow (which cannot finish inside 3.0 s) has no row there.
#   Background metrics therefore come from flow_summary and the link timeseries.
import csv
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'
ARMS = ['d1_dcqcn', 'd2_caponly', 'd3_capmig', 'd4_capmigband']
C_BPS = 10000000000.0          # bottleneck line rate
Q_ABS = 1048575                # frozen absolute queue bound, bytes
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


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    i = int(round((len(s) - 1) * q))
    return s[i]


def pick(cols, *pats):
    for p in pats:
        for c in cols:
            if re.search(p, c, re.I):
                return c
    return None


def arm(tag):
    d = os.path.join(B, '%s_out' % tag)
    conf = os.path.join(B, '%s.txt' % tag)
    if not os.path.isfile(os.path.join(d, 'DONE')):
        return dict(arm=tag, status='NOT_DONE')

    ft = rd(os.path.join(d, 'flow_timing.csv'))
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    ts = rd(os.path.join(d, 'selected_link_timeseries.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
    rt = rd(os.path.join(d, 'rate_transition.csv'))
    rs = rd(os.path.join(d, 'round_summary.csv'))

    o = dict(arm=tag, status='OK',
             cc_mode=cfg(conf, 'CC_MODE'),
             migrate=cfg(conf, 'CBAP_MIGRATION_ENABLE', '-'),
             band=cfg(conf, 'CBAP_QUEUE_BAND_ENABLE', '-'),
             cap_frac=cfg(conf, 'CBAP_STEADY_CAP_FRACTION', '-'))

    # ---------- per-flow FCT from first data tx to last ack ---------------
    inc = [r for r in ft if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN]
    fcts, ready, release, lastack = [], [], [], []
    zero_firsttx = 0
    for r in inc:
        a = f(r, 'last_ack_ns')
        t0 = f(r, 'first_data_tx_ns')
        if a is None or t0 is None:
            continue
        if t0 == 0:
            zero_firsttx += 1
            continue
        fcts.append((a - t0) / 1e6)          # ms
        lastack.append(a)
        rv, nv = f(r, 'application_ready_ns'), f(r, 'network_release_ns')
        if rv:
            ready.append(rv)
        if nv:
            release.append(nv)

    o['incast_flows_timed'] = len(fcts)
    o['first_tx_missing'] = zero_firsttx
    o['FCT_mean_ms'] = (sum(fcts) / len(fcts)) if fcts else None
    o['FCT_p95_ms'] = pct(fcts, 0.95)
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    o['FCT_max_ms'] = max(fcts) if fcts else None

    # batch reference points
    app_start = min([f(r, 'app_start_ns') for r in inc
                     if f(r, 'app_start_ns') is not None] or [None])
    readyNs = min(ready) if ready else app_start
    relNs = min(release) if release else app_start
    lastNs = max(lastack) if lastack else None
    o['application_ready_s'] = (readyNs / 1e9) if readyNs else None
    o['network_release_s'] = (relNs / 1e9) if relNs else None
    o['last_ack_s'] = (lastNs / 1e9) if lastNs else None
    o['has_admission_stage'] = bool(ready and release and relNs != readyNs)
    o['CCT_ms'] = ((lastNs - readyNs) / 1e6) if (lastNs and readyNs) else None
    o['BCT_ms'] = ((lastNs - relNs) / 1e6) if (lastNs and relNs) else None
    o['CCT_minus_BCT_us'] = ((relNs - readyNs) / 1e3) \
        if (readyNs and relNs) else None

    # injection_end, reported separately -- never BCT
    ie = [f(r, 'injection_end_time') for r in rs
          if f(r, 'injection_end_time')]
    o['injection_end_s'] = max(ie) if ie else None

    # ---------- goodput ---------------------------------------------------
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['incast_bytes'] = inc_bytes
    # measured over the CCT window so every arm uses the same clock
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - readyNs)) \
        if (lastNs and readyNs and lastNs > readyNs) else None
    o['utilisation_of_C'] = (o['batch_goodput_Gbps'] / (C_BPS / 1e9)) \
        if o['batch_goodput_Gbps'] else None

    # ---------- background ------------------------------------------------
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))
    bgcap = float(cfg(conf, 'APP_RATE_CAP_BPS', '8000000000'))
    if bg:
        r = bg[0]
        acked = f(r, 'acked_bytes', 0) or 0
        st = f(r, 'start_time', 0.5) or 0.5
        ent = bgcap / 8.0 * (stop - st)         # byte entitlement at the cap
        o['bg_flow_id'] = r.get('flow_id')
        o['bg_acked_bytes'] = acked
        o['bg_goodput_Gbps'] = acked * 8.0 / ((stop - st) * 1e9)
        o['bg_retention_pct'] = 100.0 * acked / ent if ent else None
        o['bg_completed'] = r.get('completed')
    else:
        o['bg_flow_id'] = None
        o['bg_retention_pct'] = None

    # ---------- queue -----------------------------------------------------
    if ts:
        cols = list(ts[0].keys())
        qc = pick(cols, r'queue.*byte', r'qlen', r'^queue')
        tc = pick(cols, r'time')
        o['queue_col'] = qc
        if qc:
            q = [f(r, qc) for r in ts]
            q = [x for x in q if x is not None]
            o['queue_mean_B'] = sum(q) / len(q) if q else None
            o['queue_p95_B'] = pct(q, 0.95)
            o['queue_p99_B'] = pct(q, 0.99)
            o['queue_max_B'] = max(q) if q else None
            o['qdelay_max_us'] = (max(q) * 8.0 / C_BPS * 1e6) if q else None
            o['over_Q_abs_samples'] = sum(1 for x in q if x > Q_ABS)
            # in-window queue, the part the batch is responsible for
            if tc:
                qw = [f(r, qc) for r in ts
                      if f(r, tc) is not None and
                      W0 <= (f(r, tc) * (1e9 if f(r, tc) < 1e6 else 1)) <= W1]
                qw = [x for x in qw if x is not None]
                o['queue_max_inwindow_B'] = max(qw) if qw else None
    # ---------- safety ----------------------------------------------------
    o['pfc_events'] = len(pf)
    o['retx_bytes'] = sum((f(r, 'retx_bytes', 0) or 0) for r in fs)
    o['retx_events'] = sum((f(r, 'retx_events', 0) or 0) for r in fs)
    log = '/work/d1234_logs/%s.log' % tag
    drops = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    drops += 1
    o['headroom_drops'] = drops

    # ---------- ownership / actuation, BOTH paths ------------------------
    if rt and 'actuation_kind' in rt[0]:
        w = [r for r in rt if W0 <= (f(r, 'time_ns') or 0) <= W1]
        kinds = {}
        for r in w:
            k = int(f(r, 'actuation_kind', -1) or -1)
            kinds[k] = kinds.get(k, 0) + 1
        o['act_setrate_dispatch'] = kinds.get(0, 0)
        o['act_setrate_noop'] = kinds.get(1, 0)
        o['act_migration_dispatch'] = kinds.get(2, 0)
        o['act_migration_noop'] = kinds.get(3, 0)
        o['act_background_rows'] = sum(1 for r in w
                                       if int(f(r, 'role', 0) or 0) == 1)
        ap = [f(r, 'applied_rate_after_bps') for r in w
              if int(f(r, 'role', 0) or 0) == 1]
        ap = [x for x in ap if x is not None]
        o['bg_applied_min_Gbps'] = (min(ap) / 1e9) if ap else None
        o['bg_applied_max_Gbps'] = (max(ap) / 1e9) if ap else None
    else:
        o['act_setrate_dispatch'] = None
    return o


rows = [arm(a) for a in ARMS]
done = [r for r in rows if r.get('status') == 'OK']
if not done:
    print('no arm has DONE yet')
    for r in rows:
        print('  %-16s %s' % (r['arm'], r['status']))
    sys.exit(3)

out = os.path.join(B, 'd1234_metrics.csv')
keys = []
for r in rows:
    for k in r:
        if k not in keys:
            keys.append(k)
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    for r in rows:
        w.writerow(r)
print('wrote %s' % out)
print('')


def show(label, key, fmt='%.4f', scale=1.0):
    line = '  %-26s' % label
    for r in rows:
        v = r.get(key)
        if v is None:
            line += ' %14s' % ('-' if r.get('status') == 'OK' else 'NOTDONE')
        elif isinstance(v, str):
            line += ' %14s' % v[:14]
        else:
            line += ' %14s' % (fmt % (v * scale))
    print(line)


print('%-28s' % 'metric' + ''.join(' %14s' % r['arm'][:14] for r in rows))
print('-' * 92)
show('cc_mode', 'cc_mode')
show('migration', 'migrate')
show('queue band', 'band')
show('cap fraction', 'cap_frac')
print('')
print('  --- completion, unified definitions ---')
show('incast flows timed', 'incast_flows_timed', '%d')
show('first_data_tx missing', 'first_tx_missing', '%d')
show('FCT mean (ms)', 'FCT_mean_ms')
show('FCT p95 (ms)', 'FCT_p95_ms')
show('FCT p99 (ms)', 'FCT_p99_ms')
show('FCT max (ms)', 'FCT_max_ms')
show('CCT (ms) [COMPARABLE]', 'CCT_ms')
show('BCT (ms) [cbap-only ref]', 'BCT_ms')
show('CCT-BCT (us)', 'CCT_minus_BCT_us', '%.1f')
show('injection_end (s)', 'injection_end_s', '%.9f')
show('has admission stage', 'has_admission_stage')
print('')
print('  --- throughput ---')
show('batch goodput (Gbps)', 'batch_goodput_Gbps')
show('utilisation of C', 'utilisation_of_C', '%.6f')
show('bg goodput (Gbps)', 'bg_goodput_Gbps')
show('bg retention (%)', 'bg_retention_pct')
print('')
print('  --- queue ---')
show('queue mean (B)', 'queue_mean_B', '%.1f')
show('queue p95 (B)', 'queue_p95_B', '%.0f')
show('queue p99 (B)', 'queue_p99_B', '%.0f')
show('queue max (B)', 'queue_max_B', '%.0f')
show('queue max in-window (B)', 'queue_max_inwindow_B', '%.0f')
show('qdelay max (us)', 'qdelay_max_us', '%.2f')
show('samples over Q_abs', 'over_Q_abs_samples', '%d')
print('')
print('  --- safety gates ---')
show('PFC events', 'pfc_events', '%d')
show('headroom drops', 'headroom_drops', '%d')
show('retx bytes', 'retx_bytes', '%.0f')
show('retx events', 'retx_events', '%.0f')
print('')
print('  --- actuation, BOTH paths ---')
show('setrate dispatch', 'act_setrate_dispatch', '%d')
show('setrate no-op', 'act_setrate_noop', '%d')
show('migration dispatch', 'act_migration_dispatch', '%d')
show('migration no-op', 'act_migration_noop', '%d')
show('background rows', 'act_background_rows', '%d')
show('bg applied min (Gbps)', 'bg_applied_min_Gbps')
show('bg applied max (Gbps)', 'bg_applied_max_Gbps')

print('')
print('=== hard gates ===')
for r in done:
    bad = []
    if (r.get('pfc_events') or 0) != 0:
        bad.append('PFC=%d' % r['pfc_events'])
    if (r.get('headroom_drops') or 0) != 0:
        bad.append('drops=%d' % r['headroom_drops'])
    if (r.get('retx_events') or 0) != 0:
        bad.append('retx=%d' % r['retx_events'])
    if r.get('bg_retention_pct') is not None and r['bg_retention_pct'] < 99.0:
        bad.append('retention=%.2f%%' % r['bg_retention_pct'])
    if r.get('queue_max_B') is not None and r['queue_max_B'] > Q_ABS:
        bad.append('Qmax=%.0fB > Q_abs=%dB' % (r['queue_max_B'], Q_ABS))
    print('  %-16s %s' % (r['arm'], 'PASS' if not bad else 'FAIL: ' +
                          ', '.join(bad)))
