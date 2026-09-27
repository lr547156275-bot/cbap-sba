# -*- coding: utf-8 -*-
# 30-cell matrix extraction: per-scenario tables (5 algorithms, DCQCN as the
# reference), final_results.csv, figure CSVs, twin byte-regressions.
# Frozen definitions throughout: FCT = last_ack - first_data_tx;
# BCT = last_ack - network_release; CCT = last_ack - (application_ready or
# release); injection_end its own column.  Candidate gates apply to cbapsba
# only; baseline violations (e.g. qmax > Q_abs) are reported in the open and
# never absorbed into any PASS.  Tolerates NOT_DONE cells (mid-flight use).
import csv
import hashlib
import os

B = '/work/simulation/experiment/scheme1_sba'
BG_MIN = 1 << 30
Q_ABS = 1048575.0
C_BPS = 10.0e9
SCEN = ['s1', 's2', 's6', 's3', 's4', 's5']
ALGOS = ['dcqcn', 'dctcp', 'timely', 'hpcc', 'cbapsba']
TWINS = [('mx_s1_dcqcn', 'sh_s1_d1'), ('mx_s1_cbapsba', 'sh_s1_b040'),
         ('mx_s2_dcqcn', 'sh_s2_d1'), ('mx_s2_cbapsba', 'sh_s2_b040'),
         ('mx_s6_dcqcn', 'sh_s6_d1'), ('mx_s6_cbapsba', 'sh_s6_b040'),
         ('mx_s3_dcqcn', 'scr8_d1'), ('mx_s3_cbapsba', 'scr8_b040'),
         ('mx_s3_hpcc', 'hp_s3'),
         ('mx_s4_dcqcn', 's4v_d1'), ('mx_s4_cbapsba', 's4v_b040'),
         ('mx_s5_dcqcn', 's5v_d1'), ('mx_s5_cbapsba', 's5v_b040')]
TWIN_FILES = ['flow_summary.csv', 'flow_timing.csv', 'round_summary.csv',
              'selected_link_timeseries.csv', 'pfc_events.csv']


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


def sha(p):
    if not os.path.isfile(p):
        return None
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


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
    rs = rd(os.path.join(d, 'round_summary.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))
    bgcap = float(cfg(conf, 'APP_RATE_CAP_BPS', '8000000000'))

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
    ie = [f(r, 'injection_end_time') for r in rs if f(r, 'injection_end_time')]
    o['injection_end_s'] = max(ie) if ie else None
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    o['utilisation_of_C'] = (o['batch_goodput_Gbps'] * 1e9 / C_BPS) \
        if o.get('batch_goodput_Gbps') else None
    all_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in fs)
    o['total_goodput_Gbps'] = all_bytes * 8.0 / ((stop - 0.5) * 1e9)

    # background (S6 has two; report sum + worst retention basis = full-run)
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    o['bg_flows'] = len(bg)
    if bg and lastNs and ref:
        o['bg_full_Gbps'] = sum((f(r, 'acked_bytes', 0) or 0) * 8.0 /
                                ((stop - (f(r, 'start_time', 0.5) or 0.5)) *
                                 1e9) for r in bg)
        # recovery from the first bg flow's commanded rate
        fts = rd(os.path.join(d, 'selected_flow_timeseries.csv'))
        bid = bg[0].get('flow_id')
        rows = [(f(r, 'time'), f(r, 'current_rate')) for r in fts
                if r.get('flow_id') == bid]
        rows = [(a, c) for a, c in rows if a is not None and c is not None]
        rows.sort()
        w0, wend = ref / 1e9, lastNs / 1e9
        pre = [c for a, c in rows if w0 - 0.05 <= a < w0]
        preR = sum(pre) / len(pre) if pre else None
        rec = None
        if preR:
            for a, c in rows:
                if a > wend and c >= 0.95 * preR:
                    rec = (a - wend) * 1e3
                    break
        o['bg_recovery_ms'] = rec if rec is not None else 'NOT_REACHED'

    # queue per link (S6: two bottlenecks)
    bylink = {}
    for r in ts:
        q = f(r, 'queue_bytes')
        if q is not None:
            bylink.setdefault(r.get('link_id', '0'), []).append(q)
    o['links'] = len(bylink)
    if bylink:
        o['queue_mean_B'] = max(sum(v) / len(v) for v in bylink.values())
        o['queue_p95_B'] = max(pct(v, 0.95) for v in bylink.values())
        o['queue_p99_B'] = max(pct(v, 0.99) for v in bylink.values())
        o['queue_max_B'] = max(max(v) for v in bylink.values())
        o['qdelay_p99_us'] = o['queue_p99_B'] * 8.0 / C_BPS * 1e6
        o['qdelay_max_us'] = o['queue_max_B'] * 8.0 / C_BPS * 1e6
        o['over_qabs_samples'] = sum(sum(1 for x in v if x > Q_ABS)
                                     for v in bylink.values())
    o['pfc'] = len(pf)
    o['retx'] = sum(int(float(r.get('retx_events', 0) or 0)) for r in fs)
    log = '/work/mx_logs/%s.log' % tag
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['drops'] = dr

    # cbap-only: zone/boost/lease/veto from controller_v2_trace
    vt = os.path.join(d, 'controller_v2_trace.csv')
    if os.path.isfile(vt):
        zres = {}
        n = nb = leases = 0
        sm = mx = 0.0
        veto = {}
        prev = 0.0
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
                    if prev == 0:
                        leases += 1
                prev = eff
        o['boost_duty_pct'] = 100.0 * nb / n if n else None
        o['boost_mean_G'] = sm / nb / 1e9 if nb else 0.0
        o['boost_max_G'] = mx / 1e9
        o['lease_grants'] = leases
        o['veto_counts'] = '|'.join('%s:%d' % (k, veto[k])
                                    for k in sorted(veto)) or '0'
        o['zones_ms'] = '/'.join('%.1f' % (zres.get(z, 0) * 5e-3)
                                 for z in ('GREEN', 'HOLD', 'DRAIN', 'RED'))
    return o


ALL = {}
for sc in SCEN:
    for algo in ALGOS:
        tag = 'mx_%s_%s' % (sc, algo)
        ALL[tag] = arm(tag)

# ---- per-scenario tables ---------------------------------------------------
out_md = open(os.path.join(B, 'matrix_report.md'), 'w')


def P(s=''):
    out_md.write(s + '\n')
    print(s)


P('# Final matrix (5 algorithms x 6 scenarios, single seed, standard '
  'baseline configs)')
P('')
P('Baselines run their standard frozen parameters; no threshold was tuned')
P('toward any target gap.  BCT and batch-goodput express one effect.')
for sc in SCEN:
    rows = [ALL['mx_%s_%s' % (sc, a)] for a in ALGOS]
    d1 = rows[0]
    P('')
    P('## %s' % sc.upper())
    P('| metric | ' + ' | '.join(ALGOS) + ' |')
    P('|' + '---|' * (len(ALGOS) + 1))

    def row(label, key, fmt='%.4f'):
        cells = []
        for r in rows:
            v = r.get(key)
            cells.append('-' if v is None else
                         (v if isinstance(v, str) else fmt % v))
        P('| %s | %s |' % (label, ' | '.join(cells)))
    row('status', 'status', '%s')
    row('incast done', 'incast_completed', '%d')
    row('CCT (ms)', 'CCT_ms')
    row('BCT (ms)', 'BCT_ms')
    row('FCT mean (ms)', 'FCT_mean_ms')
    row('FCT p95 (ms)', 'FCT_p95_ms')
    row('FCT p99 (ms)', 'FCT_p99_ms')
    row('injection_end (s)', 'injection_end_s', '%.6f')
    row('batch goodput (G)', 'batch_goodput_Gbps')
    row('utilisation', 'utilisation_of_C', '%.6f')
    row('total goodput (G)', 'total_goodput_Gbps')
    row('bg full (G)', 'bg_full_Gbps')
    row('bg recovery (ms)', 'bg_recovery_ms')
    row('queue p99 worst-link (B)', 'queue_p99_B', '%.0f')
    row('queue max worst-link (B)', 'queue_max_B', '%.0f')
    row('qdelay p99 (us)', 'qdelay_p99_us', '%.2f')
    row('qdelay max (us)', 'qdelay_max_us', '%.2f')
    row('samples over Q_abs', 'over_qabs_samples', '%d')
    row('PFC', 'pfc', '%d')
    row('drops', 'drops', '%d')
    row('retx', 'retx', '%d')
    row('zones G/H/D/R (ms)', 'zones_ms', '%s')
    row('boost duty (%)', 'boost_duty_pct', '%.2f')
    row('lease grants', 'lease_grants', '%d')
    row('veto counts', 'veto_counts', '%s')
    P('')
    for r in rows:
        if r.get('status') != 'OK':
            P('- %s: %s' % (r['arm'], r['status']))
            continue
        role = 'candidate' if r['arm'].endswith('cbapsba') \
            else 'baseline, report-only'
        g = []
        if r['incast_completed'] != r['incast_expected']:
            g.append('incast=%d/%d' % (r['incast_completed'],
                                       r['incast_expected']))
        for k in ('pfc', 'drops', 'retx'):
            if (r.get(k) or 0) != 0:
                g.append('%s=%d' % (k, r[k]))
        if r.get('queue_max_B') and r['queue_max_B'] > Q_ABS:
            g.append('qmax>Q_abs')
        if role == 'candidate' and d1.get('bg_full_Gbps') and \
                r.get('bg_full_Gbps') and \
                r['bg_full_Gbps'] / d1['bg_full_Gbps'] < 0.99:
            g.append('bg_full<0.99*D1')
        P('- %s [%s] gates: %s' % (r['arm'], role,
                                   'PASS' if not g else 'FAIL: ' + ', '.join(g)))
    if d1.get('CCT_ms'):
        for a in ALGOS[1:]:
            r = ALL['mx_%s_%s' % (sc, a)]
            if r.get('CCT_ms'):
                P('- %s vs dcqcn CCT: %+.2f%%' %
                  (a, (r['CCT_ms'] - d1['CCT_ms']) / d1['CCT_ms'] * 100))

# ---- twin byte-regression ---------------------------------------------------
P('')
P('## Twin byte-regression (slimming must be behaviour-neutral)')
for mx, twin in TWINS:
    if not os.path.isfile(os.path.join(B, '%s_out/DONE' % mx)):
        P('- %s: NOT_DONE' % mx)
        continue
    if not os.path.isdir(os.path.join(B, '%s_out' % twin)):
        P('- %s vs %s: twin absent (deleted), skipped' % (mx, twin))
        continue
    diff = [fn for fn in TWIN_FILES
            if sha(os.path.join(B, '%s_out/%s' % (mx, fn))) !=
            sha(os.path.join(B, '%s_out/%s' % (twin, fn)))]
    P('- %s vs %s: %s' % (mx, twin,
                          'identical (%d files)' % len(TWIN_FILES)
                          if not diff else 'DIFFERS: ' + ','.join(diff)))

# ---- final_results.csv + figdata -------------------------------------------
keys = []
for r in ALL.values():
    for k in r:
        if k not in keys:
            keys.append(k)
with open(os.path.join(B, 'final_results.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    for sc in SCEN:
        for a in ALGOS:
            w.writerow(ALL['mx_%s_%s' % (sc, a)])
fig = os.path.join(B, 'figdata')
if not os.path.isdir(fig):
    os.makedirs(fig)
for metric in ('CCT_ms', 'FCT_p99_ms', 'batch_goodput_Gbps', 'queue_p99_B',
               'queue_max_B', 'qdelay_max_us', 'bg_full_Gbps',
               'bg_recovery_ms', 'total_goodput_Gbps'):
    with open(os.path.join(fig, '%s.csv' % metric), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['scenario', 'algorithm', metric])
        for sc in SCEN:
            for a in ALGOS:
                w.writerow([sc, a, ALL['mx_%s_%s' % (sc, a)].get(metric)])
print('')
print('wrote matrix_report.md, final_results.csv, figdata/*.csv')
