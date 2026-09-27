# -*- coding: utf-8 -*-
# Shakedown acceptance.  This round asks "does it run, complete, stay safe,
# and produce sane unified metrics" -- NOT who wins.  Per-scenario D1 vs b040
# deltas are informational; no verdict is upgraded or downgraded here.
# Smoke cells additionally check the algorithm actually ENGAGED:
#   dctcp : ECN marks observed on the bottleneck
#   timely: per-flow rate actually varies (RTT-gradient control acting)
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


def arm(tag):
    d = os.path.join(B, '%s_out' % tag)
    o = dict(arm=tag)
    if not os.path.isfile(os.path.join(d, 'DONE')):
        o['status'] = 'NOT_DONE'
        log = '/work/shake_logs/%s.log' % tag
        if os.path.isfile(log):
            with open(log, errors='replace') as fh:
                for ln in fh:
                    if 'CONFIG_ERROR' in ln or 'what()' in ln:
                        o['status'] = 'FAILED: ' + ln.strip()[:90]
                        break
        return o
    o['status'] = 'OK'
    ft = rd(os.path.join(d, 'flow_timing.csv'))
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    ts = rd(os.path.join(d, 'selected_link_timeseries.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
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
    o['FCT_p99_ms'] = pct(fcts, 0.99)
    lastNs = max(lastack) if lastack else None
    ref = (min(ready) if ready else None) or \
        (min(release) if release else None)
    o['CCT_ms'] = ((lastNs - ref) / 1e6) if (lastNs and ref) else None
    inc_bytes = sum((f(r, 'acked_bytes', 0) or 0) for r in inc)
    o['batch_goodput_Gbps'] = (inc_bytes * 8.0 / (lastNs - ref)) \
        if (lastNs and ref and lastNs > ref) else None
    # queue per link (S6 has two)
    bylink = {}
    ecn = 0
    for r in ts:
        q = f(r, 'queue_bytes')
        lk = r.get('link_id', '0')
        if q is not None:
            bylink.setdefault(lk, []).append(q)
        e = f(r, 'ecn_marks_delta')
        if e:
            ecn += e
    o['links_traced'] = len(bylink)
    o['queue_p99_B'] = '/'.join('%.0f' % pct(v, 0.99) for _, v in
                                sorted(bylink.items()))
    o['queue_max_B'] = '/'.join('%.0f' % max(v) for _, v in
                                sorted(bylink.items()))
    o['queue_max_worst'] = max((max(v) for v in bylink.values()),
                               default=None)
    o['ecn_marks'] = int(ecn)
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= BG_MIN]
    o['bg_flows'] = len(bg)
    o['bg_acked_GB'] = sum((f(r, 'acked_bytes', 0) or 0) for r in bg) / 1e9
    o['pfc'] = len(pf)
    o['retx'] = sum(int(float(r.get('retx_events', 0) or 0)) for r in fs)
    log = '/work/shake_logs/%s.log' % tag
    dr = 0
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    o['drops'] = dr
    # timely engagement: does any incast flow's commanded rate vary?
    fts = os.path.join(d, 'selected_flow_timeseries.csv')
    if os.path.isfile(fts):
        rates = set()
        with open(fts) as fh:
            rr = csv.DictReader(fh)
            for i, r in enumerate(rr):
                if r.get('flow_id') not in ('0', '1'):
                    v = r.get('current_rate')
                    if v:
                        rates.add(v)
                if len(rates) > 3 or i > 200000:
                    break
        o['rate_varies'] = len(rates) > 3
    return o


print('%-14s %-28s %6s %10s %9s %8s %14s %16s %5s %4s %4s %4s' %
      ('cell', 'status', 'inc', 'CCT_ms', 'FCTp99', 'goodput',
       'q_p99(B)', 'q_max(B)', 'links', 'PFC', 'drop', 'retx'))
rows = {}
for tag in ('sh_s1_d1', 'sh_s1_b040', 'sh_s2_d1', 'sh_s2_b040',
            'sh_s6_d1', 'sh_s6_b040', 'sm_s1_dctcp', 'sm_s1_timely'):
    o = arm(tag)
    rows[tag] = o
    print('%-14s %-28s %3s/%-3s %10s %9s %8s %14s %16s %5s %4s %4s %4s' %
          (tag, o.get('status', '?')[:28],
           o.get('incast_completed', '-'), o.get('incast_expected', '-'),
           ('%.4f' % o['CCT_ms']) if o.get('CCT_ms') else '-',
           ('%.3f' % o['FCT_p99_ms']) if o.get('FCT_p99_ms') else '-',
           ('%.4f' % o['batch_goodput_Gbps'])
           if o.get('batch_goodput_Gbps') else '-',
           o.get('queue_p99_B', '-'), o.get('queue_max_B', '-'),
           o.get('links_traced', '-'), o.get('pfc', '-'),
           o.get('drops', '-'), o.get('retx', '-')))

print('')
print('=== shakedown verdicts ===')
for sc in ('s1', 's2', 's6'):
    d1 = rows.get('sh_%s_d1' % sc, {})
    b4 = rows.get('sh_%s_b040' % sc, {})
    ok = []
    for o, name in ((d1, 'd1'), (b4, 'b040')):
        if o.get('status') != 'OK':
            ok.append('%s:%s' % (name, o.get('status')))
            continue
        g = []
        if o['incast_completed'] != o['incast_expected']:
            g.append('incomplete')
        if (o['pfc'] or 0) + (o['drops'] or 0) + (o['retx'] or 0) > 0:
            g.append('unsafe')
        if name == 'b040' and o.get('queue_max_worst') and \
                o['queue_max_worst'] > Q_ABS:
            g.append('qmax>Q_abs')
        ok.append('%s:%s' % (name, 'OK' if not g else '+'.join(g)))
    line = '  %s: %s' % (sc.upper(), '  '.join(ok))
    if d1.get('CCT_ms') and b4.get('CCT_ms'):
        dl = (b4['CCT_ms'] - d1['CCT_ms']) / d1['CCT_ms'] * 100
        line += '   b040 vs D1 CCT %+.2f%% (informational)' % dl
    print(line)
print('')
for tag, need in (('sm_s1_dctcp', 'ecn'), ('sm_s1_timely', 'rate')):
    o = rows.get(tag, {})
    if o.get('status') != 'OK':
        print('  %s: %s' % (tag, o.get('status')))
        continue
    if need == 'ecn':
        eng = (o.get('ecn_marks') or 0) > 0
        ev = 'ecn_marks=%s' % o.get('ecn_marks')
    else:
        eng = bool(o.get('rate_varies'))
        ev = 'rate_varies=%s' % o.get('rate_varies')
    print('  %s: %s (%s), %s/%s complete, PFC=%s drops=%s retx=%s' %
          (tag, 'ENGAGED' if eng else 'NOT_ENGAGED', ev,
           o.get('incast_completed'), o.get('incast_expected'),
           o.get('pfc'), o.get('drops'), o.get('retx')))
