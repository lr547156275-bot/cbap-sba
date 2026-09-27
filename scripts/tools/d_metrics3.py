# -*- coding: utf-8 -*-
# Screening analysis for the 7-cell D4v2 matrix.
#
# BACKGROUND-FLOW METRICS (round 修正口径):
#   The old ">=99% retention inside the incast window" gate is REMOVED -- DCQCN
#   itself fails it (3.04%), so it measured the scenario, not the algorithm.
#   Instead, four explicit figures, each also as a ratio vs the same-seed D1:
#     bg_goodput_full_run        acked*8/(stop-0.5s)
#     bg_goodput_incast_window   snd_una delta over [2.0s, own last_ack]
#     bg_goodput_outside_window  (acked - window bytes) over remaining time
#     bg_recovery_ms             first t > last_ack where the bg flow's
#                                commanded rate >= 95% of its pre-handoff rate
#                                (pre-handoff = mean current_rate in [1.95,2.0))
#   The in-window drop is reported as an explicit trade-off, not a failure.
#
# HARD GATES: bg_full/D1 >= 99%; bg_outside/D1 >= 99%; PFC=0; drops=0; retx=0;
#             64/64 incast completed; qmax <= Q_abs.
#
# DECISION (among gate-passers, in order): 1) CCT/BCT/p99 FCT vs D1;
# 2) batch goodput vs D1; 3) bg full-run >= 99% D1 (gate); 4) queue p99/max.
# |diff| < 0.3% on a single seed => TIE_CANDIDATE, never a win/loss claim.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
PFX = sys.argv[1] if len(sys.argv) > 1 else 'scr7'   # e.g. scr8 after the fix
ARMS = ['%s_%s' % (PFX, a) for a in
        ('d1', 'd3', 'b005', 'b010', 'b020', 'b040', 'b080')]
D1 = '%s_d1' % PFX
C_BPS = 10.0e9
BG_MIN = 1 << 30
TIE = 0.003          # single-seed tie band, 0.3%
W0 = 2.0             # batch release, seconds


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


def cfg(path, k, d=None):
    if not os.path.isfile(path):
        return d
    with open(path) as fh:
        for ln in fh:
            w = ln.split()
            if len(w) >= 2 and w[0] == k:
                return w[1]
    return d


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[int(round((len(s) - 1) * q))]


def thresholds(conf):
    # Derive the four frozen bounds from the cell's own config; frozen
    # defaults (with a note) if the keys are absent (the DCQCN cell).
    hard_us = float(cfg(conf, 'CBAP_QC_APP_HARD_DELAY_US', '838.86'))
    margin = float(cfg(conf, 'CBAP_QC_SAFETY_MARGIN_BYTES', '67072'))
    soft = float(cfg(conf, 'CBAP_QC_SOFT_FRACTION', '0.5'))
    mbr = float(cfg(conf, 'CBAP_QC_MAX_BOOST_RATIO', '0.30'))
    hg_us = float(cfg(conf, 'CBAP_QC_H_GUARD_US', '175'))
    q_abs = hard_us * 1e-6 * C_BPS / 8.0
    q_red = q_abs - margin
    q_high = q_red - mbr * C_BPS * hg_us * 1e-6 / 8.0
    q_low = soft * q_abs
    basis = 'config' if cfg(conf, 'CBAP_QC_APP_HARD_DELAY_US') else \
        'frozen_default'
    return q_low, q_high, q_red, q_abs, basis


def runs_above(ts_rows, thr):
    # total time and longest consecutive run with queue_bytes > thr (ms)
    total = 0.0
    longest = 0.0
    cur = 0.0
    prev_t = None
    for r in ts_rows:
        tsec = f(r, 'time')
        q = f(r, 'queue_bytes')
        if tsec is None or q is None:
            continue
        dt = (tsec - prev_t) if prev_t is not None else 0.0
        prev_t = tsec
        if dt < 0 or dt > 0.01:
            dt = 0.0
        if q > thr:
            total += dt
            cur += dt
            if cur > longest:
                longest = cur
        else:
            cur = 0.0
    return total * 1e3, longest * 1e3


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
    pf = rd(os.path.join(d, 'pfc_events.csv'))

    o['cc_mode'] = cfg(conf, 'CC_MODE')
    o['bmax_ratio'] = cfg(conf, 'CBAP_QB2_BMAX_RATIO', '-')
    o['qb2'] = cfg(conf, 'CBAP_QUEUE_BAND_V2_ENABLE', '0')
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))
    qLow, qHigh, qRed, qAbs, basis = thresholds(conf)
    o['thresholds_basis'] = basis
    o['q_abs_B'] = qAbs

    # ---- completion, unified definitions (frozen) -------------------------
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
    o['incast_completed'] = len(fcts)
    o['incast_expected'] = 64
    o['FCT_mean_ms'] = sum(fcts) / len(fcts) if fcts else None
    o['FCT_p95_ms'] = pct(fcts, 0.95)
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    lastNs = max(lastack) if lastack else None
    readyNs = min(ready) if ready else None
    relNs = min(release) if release else None
    ref = readyNs or relNs           # D1: release == 2.0 s == CBAP ready
    o['CCT_ms'] = ((lastNs - ref) / 1e6) if (lastNs and ref) else None
    o['BCT_ms'] = ((lastNs - relNs) / 1e6) if (lastNs and relNs) else None
    o['last_ack_s'] = (lastNs / 1e9) if lastNs else None

    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    all_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in fs)
    o['total_system_goodput_Gbps'] = all_bytes * 8.0 / ((stop - 0.5) * 1e9)

    # ---- background flow, four-figure口径 ---------------------------------
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    if bg and lastNs:
        r0 = bg[0]
        bid = r0.get('flow_id')
        acked = f(r0, 'acked_bytes', 0) or 0
        st = f(r0, 'start_time', 0.5) or 0.5
        wend = lastNs / 1e9
        o['bg_goodput_full_Gbps'] = acked * 8.0 / ((stop - st) * 1e9)
        # per-flow timeseries: bytes acked inside the batch window + recovery
        fts = rd(os.path.join(d, 'selected_flow_timeseries.csv'))
        rows = [(f(r, 'time'), f(r, 'snd_una'), f(r, 'current_rate'))
                for r in fts if r.get('flow_id') == bid]
        rows = [(a, b, c) for a, b, c in rows if a is not None]
        rows.sort()
        inw = [(a, b) for a, b, c in rows if W0 <= a <= wend and b is not None]
        if len(inw) >= 2:
            wb = inw[-1][1] - inw[0][1]
            wdt = inw[-1][0] - inw[0][0]
            o['bg_goodput_inwin_Gbps'] = wb * 8.0 / (wdt * 1e9) if wdt > 0 \
                else None
            out_bytes = acked - wb
            out_dt = (stop - st) - wdt
            o['bg_goodput_outwin_Gbps'] = out_bytes * 8.0 / (out_dt * 1e9) \
                if out_dt > 0 else None
        else:
            o['bg_goodput_inwin_Gbps'] = None
            o['bg_goodput_outwin_Gbps'] = None
        pre = [c for a, b, c in rows if 1.95 <= a < 2.0 and c is not None]
        preR = sum(pre) / len(pre) if pre else None
        o['bg_prehandoff_rate_Gbps'] = (preR / 1e9) if preR else None
        rec = None
        if preR:
            for a, b, c in rows:
                if a > wend and c is not None and c >= 0.95 * preR:
                    rec = (a - wend) * 1e3
                    break
        o['bg_recovery_ms'] = rec if rec is not None else 'NOT_REACHED'
    # ---- queue -------------------------------------------------------------
    q = [f(r, 'queue_bytes') for r in ts]
    q = [x for x in q if x is not None]
    if q:
        o['queue_mean_B'] = sum(q) / len(q)
        o['queue_p95_B'] = pct(q, 0.95)
        o['queue_p99_B'] = pct(q, 0.99)
        o['queue_max_B'] = max(q)
        o['qdelay_mean_us'] = o['queue_mean_B'] * 8.0 / C_BPS * 1e6
        o['qdelay_p99_us'] = o['queue_p99_B'] * 8.0 / C_BPS * 1e6
        o['qdelay_max_us'] = o['queue_max_B'] * 8.0 / C_BPS * 1e6
        for name, thr in (('qlow', qLow), ('qhigh', qHigh), ('qred', qRed),
                          ('qabs', qAbs)):
            tot, lng = runs_above(ts, thr)
            o['over_%s_ms' % name] = tot
            o['over_%s_longest_ms' % name] = lng
    # ---- boost usage from controller_v2_trace ------------------------------
    vt = os.path.join(d, 'controller_v2_trace.csv')
    if os.path.isfile(vt):
        n = 0
        nb = 0
        sm = 0.0
        mx = 0.0
        act = 0
        with open(vt) as fh:
            hdr = None
            for ln in fh:
                if ln.startswith('#'):
                    continue
                if hdr is None:
                    hdr = ln.strip().split(',')
                    bi = hdr.index('boost_effective_bps')
                    ai = hdr.index('batch_active')
                    continue
                w = ln.strip().split(',')
                if len(w) <= max(bi, ai):
                    continue
                n += 1
                try:
                    b = float(w[bi])
                    a = int(w[ai])
                except ValueError:
                    continue
                act += a
                if b > 0:
                    nb += 1
                    sm += b
                    if b > mx:
                        mx = b
        o['boost_epochs'] = n
        o['boost_duty_pct'] = 100.0 * nb / n if n else None
        o['boost_mean_Gbps'] = (sm / nb / 1e9) if nb else 0.0
        o['boost_max_Gbps'] = mx / 1e9
        o['batch_active_epochs'] = act
    # ---- safety ------------------------------------------------------------
    o['pfc_events'] = len(pf)
    o['retx_events'] = sum((f(r, 'retx_events', 0) or 0) for r in fs)
    log = '/work/%s_logs/%s.log' % (PFX.replace('scr', 'screen'), tag)
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['headroom_drops'] = dr
    return o


rows = [arm(a) for a in ARMS]
byarm = {r['arm']: r for r in rows}
d1 = byarm.get(D1, {})


def ratio(r, k):
    a, b = r.get(k), d1.get(k)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b:
        return a / b
    return None


# ratios vs D1 + gates
for r in rows:
    if r.get('status') != 'OK':
        continue
    r['bg_full_vs_d1'] = ratio(r, 'bg_goodput_full_Gbps')
    r['bg_inwin_vs_d1'] = ratio(r, 'bg_goodput_inwin_Gbps')
    r['bg_outwin_vs_d1'] = ratio(r, 'bg_goodput_outwin_Gbps')
    g = []
    if (r.get('pfc_events') or 0) != 0:
        g.append('PFC=%d' % r['pfc_events'])
    if (r.get('headroom_drops') or 0) != 0:
        g.append('drops=%d' % r['headroom_drops'])
    if (r.get('retx_events') or 0) != 0:
        g.append('retx=%d' % r['retx_events'])
    if r.get('incast_completed') != 64:
        g.append('incast=%s/64' % r.get('incast_completed'))
    if r.get('queue_max_B') is not None and r['queue_max_B'] > r['q_abs_B']:
        g.append('qmax=%.0f>Q_abs' % r['queue_max_B'])
    if r['arm'] != D1:
        if r.get('bg_full_vs_d1') is not None and r['bg_full_vs_d1'] < 0.99:
            g.append('bg_full=%.4f<0.99*D1' % r['bg_full_vs_d1'])
        if r.get('bg_outwin_vs_d1') is not None and \
                r['bg_outwin_vs_d1'] < 0.99:
            g.append('bg_outwin=%.4f<0.99*D1' % r['bg_outwin_vs_d1'])
    r['gates'] = 'PASS' if not g else 'FAIL: ' + ', '.join(g)


def cmp_d1(r, k, lower_better):
    a, b = r.get(k), d1.get(k)
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and b):
        return 'N/A'
    dlt = (a - b) / b
    if abs(dlt) < TIE:
        return 'TIE_CANDIDATE(%+.2f%%)' % (dlt * 100)
    good = (dlt < 0) if lower_better else (dlt > 0)
    return '%s(%+.2f%%)' % ('better' if good else 'worse', dlt * 100)


out = os.path.join(B, '%s_summary.csv' % PFX.replace('scr', 'screen'))
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

md = os.path.join(B, '%s_report.md' % PFX.replace('scr', 'screen'))
with open(md, 'w') as fh:
    def P(s=''):
        fh.write(s + '\n')
        print(s)
    P('# D4v2 screening (S3, single seed, serial)')
    P('')
    P('Single-seed rule: |diff| < 0.3% vs D1 = TIE_CANDIDATE; multi-seed')
    P('paired runs are required before any win/loss claim inside that band.')
    P('In-window background degradation is an explicit trade-off, NOT a')
    P('retention failure (D1 itself drops to ~3% in-window).')
    P('')
    hdr = ('| metric | ' + ' | '.join(a.replace('scr7_', '') for a in ARMS)
           + ' |')
    P(hdr)
    P('|' + '---|' * (len(ARMS) + 1))

    def row(label, key, fmt='%.4f'):
        cells = []
        for a in ARMS:
            v = byarm.get(a, {}).get(key)
            if v is None:
                cells.append('-')
            elif isinstance(v, str):
                cells.append(v)
            else:
                cells.append(fmt % v)
        P('| %s | %s |' % (label, ' | '.join(cells)))

    row('status', 'status', '%s')
    row('BMAX ratio', 'bmax_ratio', '%s')
    row('CCT (ms)', 'CCT_ms')
    row('BCT (ms)', 'BCT_ms')
    row('FCT mean (ms)', 'FCT_mean_ms')
    row('FCT p95 (ms)', 'FCT_p95_ms')
    row('FCT p99 (ms)', 'FCT_p99_ms')
    row('batch goodput (G)', 'batch_goodput_Gbps')
    row('total system goodput (G)', 'total_system_goodput_Gbps')
    row('bg full (G)', 'bg_goodput_full_Gbps')
    row('bg full /D1', 'bg_full_vs_d1', '%.4f')
    row('bg in-window (G)', 'bg_goodput_inwin_Gbps')
    row('bg in-window /D1', 'bg_inwin_vs_d1', '%.4f')
    row('bg outside (G)', 'bg_goodput_outwin_Gbps')
    row('bg outside /D1', 'bg_outwin_vs_d1', '%.4f')
    row('bg recovery (ms)', 'bg_recovery_ms')
    row('queue mean (B)', 'queue_mean_B', '%.0f')
    row('queue p95 (B)', 'queue_p95_B', '%.0f')
    row('queue p99 (B)', 'queue_p99_B', '%.0f')
    row('queue max (B)', 'queue_max_B', '%.0f')
    row('qdelay mean (us)', 'qdelay_mean_us', '%.2f')
    row('qdelay p99 (us)', 'qdelay_p99_us', '%.2f')
    row('qdelay max (us)', 'qdelay_max_us', '%.2f')
    row('over Q_low (ms)', 'over_qlow_ms', '%.2f')
    row('over Q_low longest (ms)', 'over_qlow_longest_ms', '%.2f')
    row('over Q_high (ms)', 'over_qhigh_ms', '%.2f')
    row('over Q_red (ms)', 'over_qred_ms', '%.2f')
    row('over Q_abs (ms)', 'over_qabs_ms', '%.2f')
    row('boost duty (%)', 'boost_duty_pct', '%.2f')
    row('boost mean (G)', 'boost_mean_Gbps')
    row('boost max (G)', 'boost_max_Gbps')
    row('PFC', 'pfc_events', '%d')
    row('drops', 'headroom_drops', '%d')
    row('retx', 'retx_events', '%d')
    row('gates', 'gates', '%s')
    P('')
    P('## Decision vs D1 (order: completion, goodput, bg, queue)')
    P('')
    for r in rows:
        if r.get('status') != 'OK' or r['arm'] == D1:
            continue
        P('- **%s** [%s]' % (r['arm'], r['gates']))
        P('  - CCT %s, BCT %s, p99 FCT %s'
          % (cmp_d1(r, 'CCT_ms', True), cmp_d1(r, 'BCT_ms', True),
             cmp_d1(r, 'FCT_p99_ms', True)))
        P('  - batch goodput %s, total goodput %s'
          % (cmp_d1(r, 'batch_goodput_Gbps', False),
             cmp_d1(r, 'total_system_goodput_Gbps', False)))
        P('  - queue p99 %s B vs D1 %s B'
          % (r.get('queue_p99_B'), d1.get('queue_p99_B')))
print('wrote %s' % md)
