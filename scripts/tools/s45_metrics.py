# -*- coding: utf-8 -*-
# S4/S5 held-out validation summary (three arms per scenario, D1 reference
# per scenario).  Frozen definitions identical to the S3 round; adds the
# section-4 extras: zone residence, lease grants, veto counts, qdelay p95.
#
# Verdict (user-frozen rule, applied to b040 vs same-scenario D1):
#   GENERALIZES          : neither scenario degrades any of CCT/BCT/p99 FCT
#                          by >0.3%, and mean CCT improvement >= 1%
#   SCENARIO_DEPENDENT   : one scenario improves >0.3%, the other degrades
#                          >0.3%
#   S3_OVERFIT_OR_MECHANISM_LIMIT : no scenario improves >0.3%
#   anything else        : reported as MIXED_INCONCLUSIVE with raw numbers
# |delta| < 0.3% on a single scenario is always TIE_CANDIDATE.
# BCT and batch-goodput improvements are ONE effect (fixed batch bytes), and
# are labelled as such.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
SCEN = {'s4': ['s4v_d1', 's4v_d3', 's4v_b040'],
        's5': ['s5v_d1', 's5v_d3', 's5v_b040']}
C_BPS = 10.0e9
BG_MIN = 1 << 30
TIE = 0.003
EPOCH_S = 5e-6


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
    hard_us = float(cfg(conf, 'CBAP_QC_APP_HARD_DELAY_US', '838.86'))
    margin = float(cfg(conf, 'CBAP_QC_SAFETY_MARGIN_BYTES', '67072'))
    soft = float(cfg(conf, 'CBAP_QC_SOFT_FRACTION', '0.5'))
    mbr = float(cfg(conf, 'CBAP_QC_MAX_BOOST_RATIO', '0.30'))
    hg = float(cfg(conf, 'CBAP_QC_H_GUARD_US', '175'))
    q_abs = hard_us * 1e-6 * C_BPS / 8.0
    q_red = q_abs - margin
    q_high = q_red - mbr * C_BPS * hg * 1e-6 / 8.0
    q_low = soft * q_abs
    return q_low, q_high, q_red, q_abs


def runs_above(ts_rows, thr):
    total = longest = cur = 0.0
    prev = None
    for r in ts_rows:
        t, q = f(r, 'time'), f(r, 'queue_bytes')
        if t is None or q is None:
            continue
        dt = (t - prev) if prev is not None else 0.0
        prev = t
        if dt < 0 or dt > 0.01:
            dt = 0.0
        if q > thr:
            total += dt
            cur += dt
            longest = max(longest, cur)
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
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))
    bgcap = float(cfg(conf, 'APP_RATE_CAP_BPS', '8000000000'))
    qLow, qHigh, qRed, qAbs = thresholds(conf)
    o['q_abs_B'] = qAbs
    o['scenario'] = cfg(conf, 'SCENARIO', '-')

    inc_fs = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN]
    o['incast_expected'] = len(inc_fs)
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
    o['FCT_mean_ms'] = sum(fcts) / len(fcts) if fcts else None
    o['FCT_p95_ms'] = pct(fcts, 0.95)
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    lastNs = max(lastack) if lastack else None
    readyNs = min(ready) if ready else None
    relNs = min(release) if release else None
    ref = readyNs or relNs
    o['CCT_ms'] = ((lastNs - ref) / 1e6) if (lastNs and ref) else None
    o['BCT_ms'] = ((lastNs - relNs) / 1e6) if (lastNs and relNs) else None
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    o['utilisation_of_C'] = (o['batch_goodput_Gbps'] * 1e9 / C_BPS) \
        if o['batch_goodput_Gbps'] else None
    all_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in fs)
    o['total_goodput_Gbps'] = all_bytes * 8.0 / ((stop - 0.5) * 1e9)

    # background: four-figure口径; in-window start = this cell's own release
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    if bg and lastNs and ref:
        r0 = bg[0]
        bid = r0.get('flow_id')
        acked = f(r0, 'acked_bytes', 0) or 0
        st = f(r0, 'start_time', 0.5) or 0.5
        w0, wend = ref / 1e9, lastNs / 1e9
        o['bg_full_Gbps'] = acked * 8.0 / ((stop - st) * 1e9)
        fts = rd(os.path.join(d, 'selected_flow_timeseries.csv'))
        rows = [(f(r, 'time'), f(r, 'snd_una'), f(r, 'current_rate'))
                for r in fts if r.get('flow_id') == bid]
        rows = [(a, b, c) for a, b, c in rows if a is not None]
        rows.sort()
        inw = [(a, b) for a, b, c in rows if w0 <= a <= wend and b is not None]
        if len(inw) >= 2:
            wb = inw[-1][1] - inw[0][1]
            wdt = inw[-1][0] - inw[0][0]
            o['bg_inwin_Gbps'] = wb * 8.0 / (wdt * 1e9) if wdt > 0 else None
            odt = (stop - st) - wdt
            o['bg_outwin_Gbps'] = (acked - wb) * 8.0 / (odt * 1e9) \
                if odt > 0 else None
        pre = [c for a, b, c in rows if w0 - 0.05 <= a < w0 and c is not None]
        preR = sum(pre) / len(pre) if pre else None
        o['bg_prehandoff_Gbps'] = (preR / 1e9) if preR else None
        rec = None
        if preR:
            for a, b, c in rows:
                if a > wend and c is not None and c >= 0.95 * preR:
                    rec = (a - wend) * 1e3
                    break
        o['bg_recovery_ms'] = rec if rec is not None else 'NOT_REACHED'

    q = [f(r, 'queue_bytes') for r in ts]
    q = [x for x in q if x is not None]
    if q:
        o['queue_mean_B'] = sum(q) / len(q)
        o['queue_p95_B'] = pct(q, 0.95)
        o['queue_p99_B'] = pct(q, 0.99)
        o['queue_max_B'] = max(q)
        for lab, qq in (('mean', o['queue_mean_B']), ('p95', o['queue_p95_B']),
                        ('p99', o['queue_p99_B']), ('max', o['queue_max_B'])):
            o['qdelay_%s_us' % lab] = qq * 8.0 / C_BPS * 1e6
        for name, thr in (('qlow', qLow), ('qhigh', qHigh), ('qred', qRed),
                          ('qabs', qAbs)):
            tot, lng = runs_above(ts, thr)
            o['over_%s_ms' % name] = tot
            o['over_%s_longest_ms' % name] = lng

    # zone residence + boost/lease/veto from controller_v2_trace (b040 only)
    vt = os.path.join(d, 'controller_v2_trace.csv')
    if os.path.isfile(vt):
        zres = {}
        n = nb = leases = 0
        sm = mx = 0.0
        veto = {}
        prev_eff = 0.0
        with open(vt) as fh:
            hdr = None
            for ln in fh:
                if ln.startswith('#'):
                    continue
                w = ln.rstrip('\n').split(',')
                if hdr is None:
                    hdr = {k: i for i, k in enumerate(w)}
                    continue
                try:
                    eff = float(w[hdr['boost_effective_bps']])
                    z = w[hdr['zone']]
                    v = w[hdr['veto_reason']]
                except (ValueError, IndexError):
                    continue
                n += 1
                zres[z] = zres.get(z, 0) + 1
                if v not in ('0', ''):
                    veto[v] = veto.get(v, 0) + 1
                if eff > 0:
                    nb += 1
                    sm += eff
                    mx = max(mx, eff)
                    if prev_eff == 0:
                        leases += 1
                prev_eff = eff
        o['boost_duty_pct'] = 100.0 * nb / n if n else None
        o['boost_mean_Gbps'] = (sm / nb / 1e9) if nb else 0.0
        o['boost_max_Gbps'] = mx / 1e9
        o['lease_grants'] = leases
        o['veto_counts'] = '|'.join('%s:%d' % (k, veto[k])
                                    for k in sorted(veto)) or '0'
        for z in ('GREEN', 'HOLD', 'DRAIN', 'RED'):
            o['zone_%s_ms' % z] = zres.get(z, 0) * EPOCH_S * 1e3

    o['pfc_events'] = len(pf)
    o['retx_events'] = sum((f(r, 'retx_events', 0) or 0) for r in fs)
    log = '/work/s45_logs/%s.log' % tag
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['headroom_drops'] = dr
    return o


ALL = {}
for sc, arms in SCEN.items():
    ALL[sc] = [arm(a) for a in arms]

rows_flat = [r for sc in ('s4', 's5') for r in ALL[sc]]
out = os.path.join(B, 's45_summary.csv')
keys = []
for r in rows_flat:
    for k in r:
        if k not in keys:
            keys.append(k)
with open(out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    for r in rows_flat:
        w.writerow(r)
print('wrote %s' % out)

md = os.path.join(B, 's45_report.md')
fh = open(md, 'w')


def P(s=''):
    fh.write(s + '\n')
    print(s)


P('# S4/S5 held-out validation (b040 unmodified from S3)')
P('')
P('Note: BCT improvement and batch-goodput improvement are the SAME effect')
P('(fixed batch bytes), reported once, not as two contributions.')
verdict_in = {}
for sc in ('s4', 's5'):
    rows = ALL[sc]
    byarm = {r['arm']: r for r in rows}
    d1 = byarm['%sv_d1' % sc]
    P('')
    P('## %s' % sc.upper())
    P('| metric | ' + ' | '.join(r['arm'] for r in rows) + ' |')
    P('|' + '---|' * (len(rows) + 1))

    def row(label, key, fmt='%.4f'):
        cells = []
        for r in rows:
            v = r.get(key)
            cells.append('-' if v is None else
                         (v if isinstance(v, str) else fmt % v))
        P('| %s | %s |' % (label, ' | '.join(cells)))
    row('status', 'status', '%s')
    row('incast done/expected', 'incast_completed', '%d')
    row('CCT (ms)', 'CCT_ms')
    row('BCT (ms)', 'BCT_ms')
    row('FCT mean (ms)', 'FCT_mean_ms')
    row('FCT p95 (ms)', 'FCT_p95_ms')
    row('FCT p99 (ms)', 'FCT_p99_ms')
    row('batch goodput (G)', 'batch_goodput_Gbps')
    row('utilisation of C', 'utilisation_of_C', '%.6f')
    row('total goodput (G)', 'total_goodput_Gbps')
    row('bg full (G)', 'bg_full_Gbps')
    row('bg in-window (G)', 'bg_inwin_Gbps')
    row('bg outside (G)', 'bg_outwin_Gbps')
    row('bg recovery (ms)', 'bg_recovery_ms')
    row('queue mean/p95/p99/max (B)', 'queue_mean_B', '%.0f')
    row('queue p95 (B)', 'queue_p95_B', '%.0f')
    row('queue p99 (B)', 'queue_p99_B', '%.0f')
    row('queue max (B)', 'queue_max_B', '%.0f')
    row('qdelay mean (us)', 'qdelay_mean_us', '%.2f')
    row('qdelay p95 (us)', 'qdelay_p95_us', '%.2f')
    row('qdelay p99 (us)', 'qdelay_p99_us', '%.2f')
    row('qdelay max (us)', 'qdelay_max_us', '%.2f')
    row('over Q_low (ms)', 'over_qlow_ms', '%.2f')
    row('over Q_high (ms)', 'over_qhigh_ms', '%.2f')
    row('over Q_red (ms)', 'over_qred_ms', '%.2f')
    row('over Q_abs (ms)', 'over_qabs_ms', '%.2f')
    row('zone GREEN/HOLD/DRAIN/RED (ms)', 'zone_GREEN_ms', '%.1f')
    row('zone HOLD (ms)', 'zone_HOLD_ms', '%.1f')
    row('zone DRAIN (ms)', 'zone_DRAIN_ms', '%.1f')
    row('zone RED (ms)', 'zone_RED_ms', '%.1f')
    row('boost duty (%)', 'boost_duty_pct', '%.2f')
    row('boost mean (G)', 'boost_mean_Gbps')
    row('boost max (G)', 'boost_max_Gbps')
    row('lease grants', 'lease_grants', '%d')
    row('veto counts', 'veto_counts', '%s')
    row('PFC', 'pfc_events', '%d')
    row('drops', 'headroom_drops', '%d')
    row('retx', 'retx_events', '%d')

    # gates + deltas vs same-scenario D1
    P('')
    for r in rows:
        if r.get('status') != 'OK':
            P('- %s NOT_DONE' % r['arm'])
            continue
        g = []
        if r.get('incast_completed') != r.get('incast_expected'):
            g.append('incast=%s/%s' % (r.get('incast_completed'),
                                       r.get('incast_expected')))
        for k, lab in (('pfc_events', 'PFC'), ('headroom_drops', 'drops'),
                       ('retx_events', 'retx')):
            if (r.get(k) or 0) != 0:
                g.append('%s=%d' % (lab, r[k]))
        if r.get('queue_max_B') and r['queue_max_B'] > r['q_abs_B']:
            g.append('qmax>Q_abs')
        if r['arm'] != d1['arm']:
            for k, lab in (('bg_full_Gbps', 'bg_full'),
                           ('bg_outwin_Gbps', 'bg_outside')):
                a, b = r.get(k), d1.get(k)
                if isinstance(a, float) and isinstance(b, float) and b and \
                        a / b < 0.99:
                    g.append('%s=%.4f<0.99*D1' % (lab, a / b))
        r['gates'] = 'PASS' if not g else 'FAIL: ' + ', '.join(g)
        # Candidate gates and baseline gates are DISTINCT judgements: the
        # baseline is never asked to pass the candidate's safety gates, and a
        # baseline violation is reported in the open, never absorbed into any
        # aggregate PASS.
        role = 'baseline, report-only' if r['arm'] == d1['arm'] \
            else 'candidate'
        P('- %s [%s] gates: %s' % (r['arm'], role, r['gates']))

    b = byarm['%sv_b040' % sc]
    if b.get('status') == 'OK' and d1.get('status') == 'OK':
        ds = {}
        for k in ('CCT_ms', 'BCT_ms', 'FCT_p99_ms'):
            ds[k] = (b[k] - d1[k]) / d1[k]
        verdict_in[sc] = dict(deltas=ds, gates=b.get('gates', 'FAIL'))
        P('- b040 vs D1: CCT %+.2f%%, BCT %+.2f%%, p99 FCT %+.2f%%'
          ' (|d|<0.3%% = TIE_CANDIDATE)'
          % (ds['CCT_ms'] * 100, ds['BCT_ms'] * 100, ds['FCT_p99_ms'] * 100))

P('')
P('## Aggregate verdict (frozen rule)')
if len(verdict_in) == 2:
    deg = {sc: any(v > TIE for v in verdict_in[sc]['deltas'].values())
           for sc in verdict_in}
    imp = {sc: verdict_in[sc]['deltas']['CCT_ms'] < -TIE for sc in verdict_in}
    gates_ok = all(verdict_in[sc]['gates'] == 'PASS' for sc in verdict_in)
    mean_cct_gain = -(verdict_in['s4']['deltas']['CCT_ms'] +
                      verdict_in['s5']['deltas']['CCT_ms']) / 2.0
    if gates_ok and not any(deg.values()) and mean_cct_gain >= 0.01:
        # single-seed hold-out pass; GENERALIZES_ACROSS_SEEDS is reserved for
        # the multi-seed/perturbation stage and must not be claimed here.
        v = 'HELD_OUT_S4_S5_PASS'
    elif (imp['s4'] and deg['s5']) or (imp['s5'] and deg['s4']):
        v = 'SCENARIO_DEPENDENT'
    elif not imp['s4'] and not imp['s5']:
        v = 'S3_OVERFIT_OR_MECHANISM_LIMIT'
    else:
        v = 'MIXED_INCONCLUSIVE (raw numbers above; frozen rule matches no branch)'
    P('- candidate (b040) gates PASS in both scenarios: %s' % gates_ok)
    for sc in ('s4', 's5'):
        d1r = {r['arm']: r for r in ALL[sc]}['%sv_d1' % sc]
        P('- baseline D1 %s: over Q_abs %.2f ms, qmax %.0f B -- baseline '
          'violation, reported in the open, never part of any PASS'
          % (sc, d1r.get('over_qabs_ms') or 0, d1r.get('queue_max_B') or 0))
    P('- degraded >0.3%%: s4=%s s5=%s; improved >0.3%%: s4=%s s5=%s'
      % (deg['s4'], deg['s5'], imp['s4'], imp['s5']))
    P('- per-scenario CCT deltas: s4=%+.2f%%, s5=%+.2f%% (reported '
      'separately; the mean below is descriptive only)'
      % (verdict_in['s4']['deltas']['CCT_ms'] * 100,
         verdict_in['s5']['deltas']['CCT_ms'] * 100))
    P('- mean CCT improvement: %.2f%%' % (mean_cct_gain * 100))
    P('')
    P('**VERDICT: %s**  (GENERALIZES_ACROSS_SEEDS requires the multi-seed '
      'stage)' % v)
else:
    P('VERDICT unavailable: %d/2 scenarios complete' % len(verdict_in))
fh.close()
print('wrote %s' % md)
