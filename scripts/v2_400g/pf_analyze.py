# -*- coding: utf-8 -*-
# v2 preflight + H_eff analyzer, ROUND 2 (criteria corrected after round-1
# findings).  Emits
#   /work/v2_400g/reports/01_preflight_results.csv
#   /work/v2_400g/reports/02_heff_measurement.csv
# and a PASS/FAIL verdict per criterion.  ANY preflight FAIL => stop, do not
# proceed to screening/pilot.
#
# Round-2 criteria changes (each was a measurement artifact, not a harness
# fault; documented in reports/03_preflight_round2_notes.md):
#   - single-flow goodput is measured over the INJECTION window (first TX ->
#     last TX + 1 pkt) from the serialization trace; round 1 divided by
#     (last_ack - first_tx), whose trailing ACK RTT is 35% of the whole FCT
#     at 400G.  The ACK tail is now its own check (0.2..2 x RTT).
#   - packet geometry is wire=1000B / payload=952B (integer-ns tx times).
#   - the burst queue check sums the backlog across ALL switches (qlen_ts.csv
#     aggregate timeseries); round 1 watched one link of a multi-tier fabric
#     and misread distributed backlog as a -95% deviation.
import csv
import os
import re

V2 = '/work/v2_400g'
RS = V2 + '/results'
LG = V2 + '/logs'
RATES = {10: 10e9, 200: 200e9, 400: 400e9}
WIRE, PAY = 1000.0, 952.0
P2W = WIRE / PAY
rows1 = []
heff_rows = []
FAILS = []


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


def log_grep(tag, pat):
    p = '%s/%s.log' % (LG, tag)
    if not os.path.isfile(p):
        return None
    for ln in open(p, errors='replace'):
        m = re.search(pat, ln)
        if m:
            return m.group(1)
    return None


print('=' * 74)
print('PREFLIGHT -- single-flow line-rate checks (injection-window based)')
for rate, C in RATES.items():
    tag = 'pf_single_%dg' % rate
    d = os.path.join(RS, tag)
    ft = rd(d + '/flow_timing.csv')
    if not ft:
        FAILS.append('%s: no flow_timing (run missing/failed)' % tag)
        continue
    r = ft[0]
    la, t0 = f(r, 'last_ack_ns'), f(r, 'first_data_tx_ns')
    size = f(r, 'total_size_bytes')
    fct_s = (la - t0) / 1e9
    line_payload = C / 1e9 / P2W
    theory_s = size * 8.0 * P2W / C
    rtt_ns = log_grep(tag, r'maxRtt=(\d+)')
    # injection window + tx gaps from the serialization trace
    gaps = []
    tx_first = tx_last = None
    p = d + '/tx_serialization.csv'
    if os.path.isfile(p):
        prev = None
        with open(p) as fh:
            hdr = None
            for ln in fh:
                w = ln.rstrip('\n').split(',')
                if hdr is None:
                    hdr = {k: i for i, k in enumerate(w)}
                    continue
                if w[hdr['event']] != 'TX_BEGIN':
                    continue
                t = int(w[hdr['time_ns']])
                if tx_first is None:
                    tx_first = t
                tx_last = t
                if prev is not None and 0 < t - prev < 1e6:
                    gaps.append(t - prev)
                prev = t
    gap_med = pct(gaps, 0.5)
    gap_theory = WIRE * 8.0 / C * 1e9
    pkt_ns = gap_theory
    inj_ns = (tx_last - tx_first + pkt_ns) if tx_first is not None else None
    goodput_inj = size * 8.0 / inj_ns if inj_ns else 0.0      # payload Gbps
    tail_ns = (la - tx_first - inj_ns) if inj_ns else None
    fs = rd(d + '/flow_summary.csv')
    ts = rd(d + '/selected_link_timeseries.csv')
    ecn = sum(f(r2, 'ecn_marks_delta', 0) or 0 for r2 in ts)
    pfc = len(rd(d + '/pfc_events.csv'))
    retx = sum(int(float(r2.get('retx_events', 0) or 0)) for r2 in fs)
    ok_good = goodput_inj >= 0.95 * line_payload
    ok_time = abs(fct_s - theory_s) / theory_s <= 0.02 + \
        (float(rtt_ns) / 1e9 / theory_s if rtt_ns else 0)
    ok_gap = gap_med is not None and abs(gap_med - gap_theory) / \
        gap_theory <= 0.02
    ok_tail = (tail_ns is not None and rtt_ns is not None and
               0.2 * float(rtt_ns) <= tail_ns <= 2.0 * float(rtt_ns))
    ok_clean = ecn == 0 and pfc == 0 and retx == 0
    for name, ok in (('inj goodput>=95%line', ok_good),
                     ('8MiB timing<=2%+RTT', ok_time),
                     ('tx gap correct', ok_gap),
                     ('ack tail ~RTT', ok_tail),
                     ('no ECN/PFC/retx', ok_clean)):
        if not ok:
            FAILS.append('%s: %s FAILED' % (tag, name))
    allok = ok_good and ok_time and ok_gap and ok_tail and ok_clean
    print('%-16s inj-goodput %.3f/%.3f G  fct %.6f vs theory %.6f s  '
          'gap %.2f/%.2f ns  ack_tail %.2f us (RTT %sns)  '
          'ecn=%d pfc=%d retx=%d  %s'
          % (tag, goodput_inj, line_payload, fct_s, theory_s,
             gap_med or -1, gap_theory,
             (tail_ns or 0) / 1e3, rtt_ns, int(ecn), pfc, retx,
             'PASS' if allok else 'FAIL'))
    rows1.append([tag, 'single', rate, round(goodput_inj, 4),
                  round(line_payload, 4), round(fct_s, 9),
                  round(theory_s, 9), gap_med, round(gap_theory, 3),
                  rtt_ns, int(ecn), pfc, retx,
                  'PASS' if allok else 'FAIL'])

print('')
print('PREFLIGHT -- 64-way CC-inert burst, aggregate fabric queue at ~1 RTT')
for rate, C in RATES.items():
    tag = 'pf_burst_%dg' % rate
    d = os.path.join(RS, tag)
    ft = rd(d + '/flow_timing.csv')
    if not ft:
        FAILS.append('%s: outputs missing' % tag)
        continue
    rel = min(f(r, 'network_release_ns') or 1e18 for r in ft
              if f(r, 'total_size_bytes', 0) < 2**30)
    rtt_ns = float(log_grep(tag, r'maxRtt=(\d+)') or 8000)
    # aggregate cross-switch queue timeseries
    q_at = peak = maxport_at = None
    p = d + '/qlen_ts.csv'
    if os.path.isfile(p):
        peak = 0.0
        with open(p) as fh:
            hdr = None
            for ln in fh:
                w = ln.rstrip('\n').split(',')
                if hdr is None:
                    hdr = {k: i for i, k in enumerate(w)}
                    continue
                t = int(w[hdr['time_ns']])
                q = int(w[hdr['total_queue_bytes']])
                mp = int(w[hdr['max_port_queue_bytes']])
                if q_at is None and t >= rel + rtt_ns:
                    q_at, maxport_at = float(q), float(mp)
                if rel <= t <= rel + 500e3 and q > peak:
                    peak = float(q)
    else:
        FAILS.append('%s: qlen_ts.csv missing' % tag)
    # bottleneck-link view kept for reference only
    q_link = None
    for r in rd(d + '/selected_link_timeseries.csv'):
        t = f(r, 'time')
        if t is not None and t >= (rel + rtt_ns) / 1e9:
            q_link = f(r, 'queue_bytes') or 0
            break
    bg_frac = 0.8
    # Per-sender injectable wire bytes in the first RTT is bounded by BOTH
    # the BDP and the message itself (round-2 finding: at 400G the message,
    # 256KiB, is smaller than the BDP, 604KB, so the fabric backlog is
    # message-limited, not BDP-limited).
    bdp_wire = C * (rtt_ns / 1e9) / 8.0
    msg_wire = 262144 * P2W
    theory = 64 * min(bdp_wire, msg_wire) + (bg_frac - 1.0) * bdp_wire
    pfc = rd(d + '/pfc_events.csv')
    t_first_pfc = (int(pfc[0]['time_ns']) - rel) / 1e3 if pfc else None
    dev = (q_at - theory) / theory * 100 if q_at is not None else None
    print('%-16s fabricQ@1RTT %.3f MB  theory %.3f MB  dev %+.1f%%  '
          'peak(500us) %.3f MB  maxport %.3f MB  bottleneck-link %.3f MB  '
          'PFC %d (first %+0.1fus)'
          % (tag, (q_at or 0) / 1048576.0, theory / 1048576.0, dev or 0,
             (peak or 0) / 1048576.0, (maxport_at or 0) / 1048576.0,
             (q_link or 0) / 1048576.0, len(pfc),
             t_first_pfc if t_first_pfc is not None else -1))
    if dev is not None and abs(dev) > 30:
        FAILS.append('%s: fabric q@1RTT deviates %.1f%% from first-order '
                     'theory -- EXPLAIN before pilot' % (tag, dev))
    rows1.append([tag, 'burst', rate, None, None, None, None, None, None,
                  int(rtt_ns), None, len(pfc), None,
                  'fabricQ@1RTT=%.3fMB theory=%.3fMB dev=%+.1f%%'
                  % ((q_at or 0) / 1048576.0, theory / 1048576.0, dev or 0)])

with open(V2 + '/reports/01_preflight_results.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['cell', 'type', 'rate_g', 'goodput_gbps', 'line_payload_g',
                'fct_s', 'theory_s', 'tx_gap_ns', 'gap_theory_ns', 'rtt_ns',
                'ecn', 'pfc', 'retx', 'verdict'])
    for r in rows1:
        w.writerow(r)

print('')
print('H_EFF -- actuation-stage measurement')
for rate in RATES:
    tag = 'heff_%dg' % rate
    d = os.path.join(RS, tag)
    p = d + '/actuation.csv'
    if not os.path.isfile(p) or os.path.getsize(p) == 0:
        print('%-12s actuation.csv missing/empty (run failed?)' % tag)
        FAILS.append('%s: actuation missing' % tag)
        continue
    by_stage = {}
    with open(p) as fh:
        hdr = None
        for ln in fh:
            w = ln.rstrip('\n').split(',')
            if hdr is None:
                hdr = {k: i for i, k in enumerate(w)}
                continue
            try:
                st = w[hdr['stage']]
                dc = float(w[hdr['delta_from_command_ns']])
            except (ValueError, IndexError, KeyError):
                continue
            by_stage.setdefault(st, []).append(dc)
    for st in sorted(by_stage):
        v = by_stage[st]
        heff_rows.append([tag, rate, st, len(v),
                          round(sum(v) / len(v) / 1e3, 3),
                          round(pct(v, 0.95) / 1e3, 3),
                          round(pct(v, 0.99) / 1e3, 3),
                          round(max(v) / 1e3, 3)])
        print('%-12s %-34s n=%-6d mean=%8.2fus p95=%8.2fus p99=%8.2fus '
              'max=%8.2fus' % (tag, st, len(v), sum(v) / len(v) / 1e3,
                               pct(v, 0.95) / 1e3, pct(v, 0.99) / 1e3,
                               max(v) / 1e3))
with open(V2 + '/reports/02_heff_measurement.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['cell', 'rate_g', 'stage', 'n', 'mean_us', 'p95_us',
                'p99_us', 'max_us'])
    for r in heff_rows:
        w.writerow(r)

print('')
print('=' * 74)
if FAILS:
    print('PREFLIGHT VERDICT: FAIL (%d) -- DO NOT proceed to screening/pilot'
          % len(FAILS))
    for s in FAILS:
        print('  !! ' + s)
else:
    print('PREFLIGHT VERDICT: PASS -- H_eff selection: use the p99 of the '
          'last stage (bottleneck-affected) per rate, rounded up; confirm '
          'before screening generation.')
