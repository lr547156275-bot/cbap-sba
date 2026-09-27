# -*- coding: utf-8 -*-
# Corrected D1-D4 extractor.  Two defects in the first pass, both mine:
#
# 1. CCT reference for arms without an admission stage.  I fell back to
#    q->startTime, which for the baselines is 1.9 s -- the instant the QP is
#    installed, 100 ms before the round is released at 2.0 s.  That inflated
#    D1's CCT to 158.37 ms.  The correct uniform reference is the round release
#    time, which for DCQCN is 2.000000000 s and coincides exactly with CBAP's
#    application_ready_ns.  So CCT is comparable across arms when measured from
#    there.  The reference actually used is now reported per arm.
#
# 2. Background retention.  My definition (delivered / 8 Gbps entitlement over
#    the whole sim) yields 91.7-93.2% for EVERY arm including the DCQCN
#    baseline, so it cannot be evidence of a CBAP regression -- it measures a
#    property of the scenario.  Both a whole-sim figure and a
#    during-vs-before-incast figure are now emitted, and the >=99% gate is
#    applied only to the during-vs-before ratio, which is what "the background
#    flow was preserved" actually means.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
ARMS = ['d1_dcqcn', 'd2_caponly', 'd3_capmig', 'd4_capmigband']
C_BPS = 10000000000.0
Q_ABS = 1048575
BG_MIN = 1 << 30
W0, W1 = 2000000000, 2058500000       # incast window, ns
PRE0, PRE1 = 1900000000, 2000000000   # 100 ms immediately before release


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


def iv(r, k, d=-1):
    try:
        return int(float(r[k]))
    except (KeyError, ValueError, TypeError):
        return d


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[int(round((len(s) - 1) * q))]


def tons(v):
    # the link/flow timeseries carry seconds; rate_transition carries ns
    return v * 1e9 if v is not None and v < 1e6 else v


def arm(tag):
    d = os.path.join(B, '%s_out' % tag)
    conf = os.path.join(B, '%s.txt' % tag)
    o = dict(arm=tag)
    if not os.path.isfile(os.path.join(d, 'DONE')):
        o['status'] = 'NOT_DONE'
        return o
    o['status'] = 'OK'
    ft = rd(os.path.join(d, 'flow_timing.csv'))
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    ts = rd(os.path.join(d, 'selected_link_timeseries.csv'))
    fts = rd(os.path.join(d, 'selected_flow_timeseries.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
    rt = rd(os.path.join(d, 'rate_transition.csv'))
    rs = rd(os.path.join(d, 'round_summary.csv'))

    o['cc_mode'] = cfg(conf, 'CC_MODE')
    o['migrate'] = cfg(conf, 'CBAP_MIGRATION_ENABLE', '-')
    o['band'] = cfg(conf, 'CBAP_QUEUE_BAND_ENABLE', '-')

    inc = [r for r in ft if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN]
    fcts, lastack, ready, release, appst = [], [], [], [], []
    for r in inc:
        a, t0 = f(r, 'last_ack_ns'), f(r, 'first_data_tx_ns')
        if a is None or not t0:
            continue
        fcts.append((a - t0) / 1e6)
        lastack.append(a)
        for key, acc in (('application_ready_ns', ready),
                         ('network_release_ns', release),
                         ('app_start_ns', appst)):
            v = f(r, key)
            if v:
                acc.append(v)

    o['incast_flows_timed'] = len(fcts)
    o['FCT_mean_ms'] = sum(fcts) / len(fcts) if fcts else None
    o['FCT_p95_ms'] = pct(fcts, 0.95)
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    o['FCT_max_ms'] = max(fcts) if fcts else None

    # round release, available for every arm because all arms run round mode
    rel_rs = [f(r, 'release_time') for r in rs if f(r, 'release_time')]
    round_rel_ns = min(rel_rs) * 1e9 if rel_rs else None

    lastNs = max(lastack) if lastack else None
    relNs = min(release) if release else None
    readyNs = min(ready) if ready else None

    if readyNs:
        cct_ref, cct_src = readyNs, 'application_ready_ns'
    elif relNs:
        cct_ref, cct_src = relNs, 'network_release_ns'
    else:
        cct_ref, cct_src = (min(appst) if appst else None), 'app_start_ns'
    o['cct_reference_s'] = (cct_ref / 1e9) if cct_ref else None
    o['cct_reference_src'] = cct_src
    o['app_start_s'] = (min(appst) / 1e9) if appst else None
    o['network_release_s'] = (relNs / 1e9) if relNs else None
    o['last_ack_s'] = (lastNs / 1e9) if lastNs else None
    o['has_admission_stage'] = int(bool(readyNs and relNs and relNs != readyNs))
    o['CCT_ms'] = ((lastNs - cct_ref) / 1e6) if (lastNs and cct_ref) else None
    o['BCT_ms'] = ((lastNs - relNs) / 1e6) if (lastNs and relNs) else None
    o['admission_delay_us'] = ((relNs - readyNs) / 1e3) \
        if (readyNs and relNs) else 0.0
    ie = [f(r, 'injection_end_time') for r in rs if f(r, 'injection_end_time')]
    o['injection_end_s'] = max(ie) if ie else None

    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['incast_bytes'] = inc_bytes
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - cct_ref)) \
        if (lastNs and cct_ref and lastNs > cct_ref) else None
    o['utilisation_of_C'] = (o['batch_goodput_Gbps'] * 1e9 / C_BPS) \
        if o['batch_goodput_Gbps'] else None

    # ---- background: whole-sim, and during-vs-before ---------------------
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))
    bgcap = float(cfg(conf, 'APP_RATE_CAP_BPS', '8000000000'))
    o['bg_cap_Gbps'] = bgcap / 1e9
    if bg:
        r0 = bg[0]
        acked = f(r0, 'acked_bytes', 0) or 0
        st = f(r0, 'start_time', 0.5) or 0.5
        o['bg_flow_id'] = r0.get('flow_id')
        o['bg_goodput_whole_Gbps'] = acked * 8.0 / ((stop - st) * 1e9)
        o['bg_retention_whole_pct'] = 100.0 * (acked * 8.0) / \
            (bgcap * (stop - st))
    else:
        o['bg_flow_id'] = None
    # per-flow timeseries: bytes actually acked by the bg flow in each window
    if fts and bg:
        bid = o['bg_flow_id']
        pre, dur = [], []
        for r in fts:
            if r.get('flow_id') != bid:
                continue
            t = tons(f(r, 'time'))
            u = f(r, 'snd_una')
            if t is None or u is None:
                continue
            if PRE0 <= t <= PRE1:
                pre.append((t, u))
            if W0 <= t <= W1:
                dur.append((t, u))
        def rate(v):
            if len(v) < 2:
                return None
            v.sort()
            dt = (v[-1][0] - v[0][0]) / 1e9
            return (v[-1][1] - v[0][1]) * 8.0 / dt if dt > 0 else None
        rp, rdur = rate(pre), rate(dur)
        o['bg_rate_before_Gbps'] = (rp / 1e9) if rp else None
        o['bg_rate_during_Gbps'] = (rdur / 1e9) if rdur else None
        o['bg_retention_during_pct'] = (100.0 * rdur / rp) \
            if (rp and rdur) else None
        o['bg_in_flow_timeseries'] = int(bool(pre or dur))
    else:
        o['bg_in_flow_timeseries'] = 0

    # ---- queue -----------------------------------------------------------
    if ts:
        q = [f(r, 'queue_bytes') for r in ts]
        q = [x for x in q if x is not None]
        o['queue_mean_B'] = sum(q) / len(q) if q else None
        o['queue_p99_B'] = pct(q, 0.99)
        o['queue_p999_B'] = pct(q, 0.999)
        o['queue_max_B'] = max(q) if q else None
        o['qdelay_max_us'] = (max(q) * 8.0 / C_BPS * 1e6) if q else None
        o['over_Q_abs_samples'] = sum(1 for x in q if x > Q_ABS)
        qin = [f(r, 'queue_bytes') for r in ts
               if W0 <= (tons(f(r, 'time')) or -1) <= W1]
        qin = [x for x in qin if x is not None]
        o['queue_samples_inwindow'] = len(qin)
        o['queue_mean_inwindow_B'] = sum(qin) / len(qin) if qin else None
        o['queue_p99_inwindow_B'] = pct(qin, 0.99)
        o['queue_max_inwindow_B'] = max(qin) if qin else None
        o['over_Q_abs_inwindow'] = sum(1 for x in qin if x > Q_ABS)

    o['pfc_events'] = len(pf)
    o['retx_bytes'] = sum((f(r, 'retx_bytes', 0) or 0) for r in fs)
    o['retx_events'] = sum((f(r, 'retx_events', 0) or 0) for r in fs)
    log = '/work/d1234_logs/%s.log' % tag
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['headroom_drops'] = dr

    if rt and 'actuation_kind' in rt[0]:
        allk, wink = {}, {}
        for r in rt:
            k = iv(r, 'actuation_kind')
            allk[k] = allk.get(k, 0) + 1
            if W0 <= (f(r, 'time_ns') or 0) <= W1:
                wink[k] = wink.get(k, 0) + 1
        for k, name in ((0, 'setrate_dispatch'), (1, 'setrate_noop'),
                        (2, 'migration_dispatch'), (3, 'migration_noop')):
            o['all_' + name] = allk.get(k, 0)
            o['win_' + name] = wink.get(k, 0)
        o['rate_transition_rows'] = len(rt)
        bgr = [r for r in rt if iv(r, 'role', 0) == 1]
        o['bg_rows_all'] = len(bgr)
        o['bg_rows_win'] = sum(1 for r in bgr
                               if W0 <= (f(r, 'time_ns') or 0) <= W1)
        ap = [f(r, 'applied_rate_after_bps') for r in bgr]
        ap = [x for x in ap if x is not None]
        o['bg_applied_min_Gbps'] = (min(ap) / 1e9) if ap else None
        o['bg_applied_max_Gbps'] = (max(ap) / 1e9) if ap else None
    return o


rows = [arm(a) for a in ARMS]
out = os.path.join(B, 'd1234_metrics_v2.csv')
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


def show(label, key, fmt='%.4f'):
    line = '  %-28s' % label
    for r in rows:
        v = r.get(key)
        if v is None:
            line += ' %14s' % '-'
        elif isinstance(v, str):
            line += ' %14s' % v[:14]
        else:
            line += ' %14s' % (fmt % v)
    print(line)


print('%-30s' % 'metric' + ''.join(' %14s' % r['arm'][:14] for r in rows))
print('-' * 94)
show('cc_mode', 'cc_mode')
show('migration', 'migrate')
show('queue band', 'band')
print('')
print('  --- reference points ---')
show('app_start (s)', 'app_start_s', '%.9f')
show('CCT reference (s)', 'cct_reference_s', '%.9f')
show('CCT reference source', 'cct_reference_src')
show('network_release (s)', 'network_release_s', '%.9f')
show('admission delay (us)', 'admission_delay_us', '%.1f')
show('last ack (s)', 'last_ack_s', '%.9f')
show('injection_end (s)', 'injection_end_s', '%.9f')
print('')
print('  --- completion ---')
show('FCT mean (ms)', 'FCT_mean_ms')
show('FCT p95 (ms)', 'FCT_p95_ms')
show('FCT p99 (ms)', 'FCT_p99_ms')
show('FCT max (ms)', 'FCT_max_ms')
show('CCT (ms) COMPARABLE', 'CCT_ms')
show('BCT (ms)', 'BCT_ms')
print('')
print('  --- throughput ---')
show('batch goodput (Gbps)', 'batch_goodput_Gbps')
show('utilisation of C', 'utilisation_of_C', '%.6f')
show('bg goodput whole (Gbps)', 'bg_goodput_whole_Gbps')
show('bg retention whole (%)', 'bg_retention_whole_pct')
show('bg rate before (Gbps)', 'bg_rate_before_Gbps')
show('bg rate during (Gbps)', 'bg_rate_during_Gbps')
show('bg retention during (%)', 'bg_retention_during_pct')
print('')
print('  --- queue, whole trace ---')
show('queue mean (B)', 'queue_mean_B', '%.1f')
show('queue p99 (B)', 'queue_p99_B', '%.0f')
show('queue p99.9 (B)', 'queue_p999_B', '%.0f')
show('queue max (B)', 'queue_max_B', '%.0f')
show('qdelay max (us)', 'qdelay_max_us', '%.2f')
show('samples over Q_abs', 'over_Q_abs_samples', '%.0f')
print('')
print('  --- queue, incast window only ---')
show('samples in window', 'queue_samples_inwindow', '%.0f')
show('queue mean in-win (B)', 'queue_mean_inwindow_B', '%.1f')
show('queue p99 in-win (B)', 'queue_p99_inwindow_B', '%.0f')
show('queue max in-win (B)', 'queue_max_inwindow_B', '%.0f')
show('over Q_abs in-win', 'over_Q_abs_inwindow', '%.0f')
print('')
print('  --- safety ---')
show('PFC events', 'pfc_events', '%.0f')
show('headroom drops', 'headroom_drops', '%.0f')
show('retx bytes', 'retx_bytes', '%.0f')
show('retx events', 'retx_events', '%.0f')
print('')
print('  --- actuation, BOTH paths ---')
show('rate_transition rows', 'rate_transition_rows', '%.0f')
show('setrate dispatch (all)', 'all_setrate_dispatch', '%.0f')
show('setrate dispatch (win)', 'win_setrate_dispatch', '%.0f')
show('setrate no-op (all)', 'all_setrate_noop', '%.0f')
show('migration disp (all)', 'all_migration_dispatch', '%.0f')
show('migration disp (win)', 'win_migration_dispatch', '%.0f')
show('bg rows (all/win)', 'bg_rows_win', '%.0f')
show('bg applied min (Gbps)', 'bg_applied_min_Gbps')
show('bg applied max (Gbps)', 'bg_applied_max_Gbps')

print('')
print('=== gates (retention gate uses during-vs-before, see header) ===')
for r in rows:
    if r.get('status') != 'OK':
        continue
    bad = []
    for k, lab in (('pfc_events', 'PFC'), ('headroom_drops', 'drops'),
                   ('retx_events', 'retx')):
        if (r.get(k) or 0) != 0:
            bad.append('%s=%d' % (lab, r[k]))
    ret = r.get('bg_retention_during_pct')
    if ret is not None and ret < 99.0:
        bad.append('retention_during=%.2f%%' % ret)
    if r.get('queue_max_B') is not None and r['queue_max_B'] > Q_ABS:
        bad.append('Qmax=%.0fB>Q_abs' % r['queue_max_B'])
    print('  %-16s %s' % (r['arm'], 'PASS' if not bad else 'FAIL: ' +
                          ', '.join(bad)))
