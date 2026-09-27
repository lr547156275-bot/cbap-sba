# -*- coding: utf-8 -*-
# Item 2 + 3 summary.
#
# A. Neighborhood on S3 (fixed seed): scr8_d1 (baseline), scr8_d3,
#    nb_b030 / scr8_b040 / nb_b050.  b040 = the frozen candidate; NOT re-run
#    (binary unchanged since scr8, deterministic sim).  Verdict rules:
#      PARAMETER_INERT      : nb cell's flow_summary byte-identical to b040's
#                             (identical output must NOT be read as robustness)
#      NEIGHBORHOOD_ROBUST  : both nb cells distinct from b040 AND beat D1 on
#                             CCT beyond the 0.3% tie band with gates PASS
#      KNIFE_EDGE_SUSPECT   : anything else (details printed)
#
# B. HPCC on S3/S4/S5 against D1/D3/b040 with the SAME frozen definitions:
#    FCT = last_ack - first_data_tx; BCT = last_ack - network_release;
#    CCT = last_ack - application_ready (D1/HPCC: release == 2.0 s reference);
#    injection_end reported in its own column, never mixed into FCT/BCT/CCT.
#    Cross-check: hp_s3 BCT should reproduce the frozen au-round HPCC figure
#    (~60.33 ms); a large deviation is a harness problem, not a result.
import csv
import hashlib
import os

B = '/work/simulation/experiment/scheme1_sba'
C_BPS = 10.0e9
BG_MIN = 1 << 30
TIE = 0.003
Q_ABS = 1048575


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


def arm(tag, logdir):
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
    o['cc_mode'] = cfg(conf, 'CC_MODE')
    o['algo'] = cfg(conf, 'ALGORITHM')
    o['bmax'] = cfg(conf, 'CBAP_QB2_BMAX_RATIO', '-')
    stop = float(cfg(conf, 'SIMULATOR_STOP_TIME', '3.0'))

    inc = [r for r in ft if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN]
    o['incast_expected'] = len([r for r in fs
                                if (f(r, 'total_size_bytes', 0) or 0) < BG_MIN])
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
    o['injection_end_s'] = max(ie) if ie else None       # OWN column only
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    o['utilisation_of_C'] = (o['batch_goodput_Gbps'] * 1e9 / C_BPS) \
        if o['batch_goodput_Gbps'] else None

    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    if bg:
        r0 = bg[0]
        acked = f(r0, 'acked_bytes', 0) or 0
        st = f(r0, 'start_time', 0.5) or 0.5
        o['bg_full_Gbps'] = acked * 8.0 / ((stop - st) * 1e9)
    q = [f(r, 'queue_bytes') for r in ts]
    q = [x for x in q if x is not None]
    if q:
        o['queue_mean_B'] = sum(q) / len(q)
        o['queue_p95_B'] = pct(q, 0.95)
        o['queue_p99_B'] = pct(q, 0.99)
        o['queue_max_B'] = max(q)
    o['pfc'] = len(pf)
    o['retx'] = sum((f(r, 'retx_events', 0) or 0) for r in fs)
    log = '%s/%s.log' % (logdir, tag)
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['drops'] = dr

    # boost / requested / applied / arrival, from controller_v2_trace
    vt = os.path.join(d, 'controller_v2_trace.csv')
    if os.path.isfile(vt):
        n = nb = act = 0
        s_req = s_app = s_arr = s_eff = 0.0
        mx = 0.0
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
                    ba = int(w[hdr['batch_active']])
                    eff = float(w[hdr['boost_effective_bps']])
                except (ValueError, IndexError):
                    continue
                n += 1
                if ba:
                    act += 1
                    s_req += float(w[hdr['boost_requested_bps']])
                    s_app += float(w[hdr['aggregate_applied_bps']])
                    s_arr += float(w[hdr['arrival_wire_bps']])
                if eff > 0:
                    nb += 1
                    s_eff += eff
                    mx = max(mx, eff)
        o['boost_on_ms'] = nb * 5e-3
        o['boost_duty_batch_pct'] = 100.0 * nb / act if act else None
        o['boost_mean_Gbps'] = s_eff / nb / 1e9 if nb else 0.0
        o['boost_max_Gbps'] = mx / 1e9
        if act:
            o['req_mean_Gbps'] = s_req / act / 1e9
            o['applied_mean_Gbps'] = s_app / act / 1e9
            o['arrival_mean_Gbps'] = s_arr / act / 1e9
    return o


def show(rows, label, key, fmt='%.4f'):
    line = '  %-26s' % label
    for r in rows:
        v = r.get(key)
        if v is None:
            line += ' %13s' % '-'
        elif isinstance(v, str):
            line += ' %13s' % v[:13]
        else:
            line += ' %13s' % (fmt % v)
    print(line)


def gates(r, d1):
    g = []
    if r.get('incast_completed') != r.get('incast_expected'):
        g.append('incast')
    for k in ('pfc', 'drops', 'retx'):
        if (r.get(k) or 0) != 0:
            g.append('%s=%d' % (k, r[k]))
    if r.get('queue_max_B') and r['queue_max_B'] > Q_ABS:
        g.append('qmax>Q_abs')
    if d1 and r is not d1:
        a, b = r.get('bg_full_Gbps'), d1.get('bg_full_Gbps')
        if isinstance(a, float) and isinstance(b, float) and b and a / b < 0.99:
            g.append('bg_full<0.99*D1')
    return 'PASS' if not g else 'FAIL: ' + ', '.join(g)


print('=' * 78)
print('A. NEIGHBORHOOD (S3, fixed seed; b040 = frozen candidate, not re-run)')
NB = ['scr8_d1', 'scr8_d3', 'nb_b030', 'scr8_b040', 'nb_b050']
nb_rows = []
for t in NB:
    logdir = '/work/screen8_logs' if t.startswith('scr8') else '/work/nbhp_logs'
    nb_rows.append(arm(t, logdir))
d1 = nb_rows[0]
print('%-28s' % 'metric' + ''.join(' %13s' % r['arm'][:13] for r in nb_rows))
print('-' * 98)
show(nb_rows, 'status', 'status', '%s')
show(nb_rows, 'BMAX', 'bmax', '%s')
show(nb_rows, 'CCT (ms)', 'CCT_ms')
show(nb_rows, 'BCT (ms)', 'BCT_ms')
show(nb_rows, 'FCT mean (ms)', 'FCT_mean_ms')
show(nb_rows, 'FCT p95 (ms)', 'FCT_p95_ms')
show(nb_rows, 'FCT p99 (ms)', 'FCT_p99_ms')
show(nb_rows, 'batch goodput (G)', 'batch_goodput_Gbps')
show(nb_rows, 'utilisation of C', 'utilisation_of_C', '%.6f')
show(nb_rows, 'queue mean (B)', 'queue_mean_B', '%.0f')
show(nb_rows, 'queue p95 (B)', 'queue_p95_B', '%.0f')
show(nb_rows, 'queue p99 (B)', 'queue_p99_B', '%.0f')
show(nb_rows, 'queue max (B)', 'queue_max_B', '%.0f')
show(nb_rows, 'boost ON (ms)', 'boost_on_ms', '%.2f')
show(nb_rows, 'boost duty in batch (%)', 'boost_duty_batch_pct', '%.2f')
show(nb_rows, 'boost mean/max (G)', 'boost_mean_Gbps')
show(nb_rows, 'boost max (G)', 'boost_max_Gbps')
show(nb_rows, 'requested mean (G)', 'req_mean_Gbps')
show(nb_rows, 'applied mean (G)', 'applied_mean_Gbps')
show(nb_rows, 'arrival mean (G)', 'arrival_mean_Gbps')
show(nb_rows, 'PFC', 'pfc', '%d')
show(nb_rows, 'drops', 'drops', '%d')
show(nb_rows, 'retx', 'retx', '%d')
print('')
for r in nb_rows:
    if r.get('status') != 'OK':
        continue
    role = 'baseline, report-only' if r['arm'] == 'scr8_d1' else 'candidate'
    print('  %s [%s] gates: %s' % (r['arm'], role, gates(r, d1)))

byarm = {r['arm']: r for r in nb_rows}
cls = []          # one classification per nb cell
detail = []
for t in ('nb_b030', 'nb_b050'):
    r = byarm.get(t, {})
    if r.get('status') != 'OK':
        detail.append('%s NOT_DONE' % t)
        cls.append('MISSING')
        continue
    ident = (sha(os.path.join(B, '%s_out/flow_summary.csv' % t)) ==
             sha(os.path.join(B, 'scr8_b040_out/flow_summary.csv')))
    dcct = (r['CCT_ms'] - d1['CCT_ms']) / d1['CCT_ms'] \
        if (r.get('CCT_ms') and d1.get('CCT_ms')) else None
    detail.append('%s: identical_to_b040=%s, CCT vs D1 %+.2f%%, gates %s'
                  % (t, ident, (dcct or 0) * 100, gates(r, d1)))
    if ident:
        cls.append('INERT')
    elif dcct is not None and dcct < -TIE and gates(r, d1) == 'PASS':
        cls.append('ROBUST')
    else:
        cls.append('KNIFE')
# priority: any knife-edge signal dominates; inert next (must not be sold as
# robustness); only two distinct-and-winning neighbors earn ROBUST.
if 'KNIFE' in cls or 'MISSING' in cls:
    verdict = 'KNIFE_EDGE_SUSPECT' if 'KNIFE' in cls else 'INCOMPLETE'
elif 'INERT' in cls:
    verdict = 'PARAMETER_INERT'
else:
    verdict = 'NEIGHBORHOOD_ROBUST'
print('')
for x in detail:
    print('  ' + x)
print('  NEIGHBORHOOD VERDICT: %s' % verdict)
if verdict == 'PARAMETER_INERT':
    print('  (identical outputs mean the parameter did not act; this must '
          'NOT be read as robustness)')

print('')
print('=' * 78)
print('B. HPCC vs D1/D3/b040 (identical topology/flows/PG/seed/definitions;')
print('   injection_end is its own column, never mixed into FCT/BCT/CCT)')
SCEN = {'S3': (['scr8_d1', 'scr8_d3', 'scr8_b040', 'hp_s3'],
               '/work/screen8_logs'),
        'S4': (['s4v_d1', 's4v_d3', 's4v_b040', 'hp_s4'], '/work/s45_logs'),
        'S5': (['s5v_d1', 's5v_d3', 's5v_b040', 'hp_s5'], '/work/s45_logs')}
for sc in ('S3', 'S4', 'S5'):
    arms, logdir = SCEN[sc]
    rows = []
    for t in arms:
        ld = '/work/nbhp_logs' if t.startswith('hp_') else logdir
        rows.append(arm(t, ld))
    d1 = rows[0]
    print('')
    print('--- %s ---' % sc)
    print('%-28s' % 'metric' + ''.join(' %13s' % r['arm'][:13] for r in rows))
    show(rows, 'status', 'status', '%s')
    show(rows, 'algo label', 'algo', '%s')
    show(rows, 'CCT (ms)', 'CCT_ms')
    show(rows, 'BCT (ms)', 'BCT_ms')
    show(rows, 'FCT mean (ms)', 'FCT_mean_ms')
    show(rows, 'FCT p95 (ms)', 'FCT_p95_ms')
    show(rows, 'FCT p99 (ms)', 'FCT_p99_ms')
    show(rows, 'injection_end (s)', 'injection_end_s', '%.6f')
    show(rows, 'batch goodput (G)', 'batch_goodput_Gbps')
    show(rows, 'utilisation of C', 'utilisation_of_C', '%.6f')
    show(rows, 'bg full (G)', 'bg_full_Gbps')
    show(rows, 'queue p99 (B)', 'queue_p99_B', '%.0f')
    show(rows, 'queue max (B)', 'queue_max_B', '%.0f')
    show(rows, 'PFC', 'pfc', '%d')
    show(rows, 'drops', 'drops', '%d')
    show(rows, 'retx', 'retx', '%d')
    for r in rows:
        if r.get('status') != 'OK':
            continue
        role = 'baseline, report-only' if r['arm'] in \
            ('scr8_d1', 's4v_d1', 's5v_d1', 'hp_s3', 'hp_s4', 'hp_s5') \
            else 'candidate'
        print('  %s [%s] gates: %s' % (r['arm'], role, gates(r, d1)))
hp3 = arm('hp_s3', '/work/nbhp_logs')
if hp3.get('BCT_ms'):
    print('')
    print('cross-check: hp_s3 BCT %.4f ms vs frozen au-round HPCC ~60.33 ms'
          % hp3['BCT_ms'])
