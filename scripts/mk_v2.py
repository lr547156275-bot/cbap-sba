# -*- coding: utf-8 -*-
# v2_400g unified config generator.  This round generates PREFLIGHT and HEFF
# cells only (screening/pilot generation is present but gated off until the
# preflight passes, per instruction).
#
# Derivations (v2 rules, from the campaign spec):
#   MIN_RATE  = MIN_RATE_FRAC * C                (payload bps, 0.01C)
#   Q_target  = C * D_target / 8
#   Q_abs     = min(C * D_abs / 8, 0.25 * BUFFER)
#   BMAX      = BMAX_RATIO * C
#   bg rate   = BG_LOAD_FRAC * C
# Q_abs is NOT bound to any message size.  All file paths absolute under
# /work/v2_400g/.
#
# Round-2 revisions (preflight round 1 findings):
#   - PACKET_PAYLOAD_SIZE 952 -> wire packet exactly 1000B, so per-packet tx
#     time is an integer nanosecond at all three rates (800/40/20ns); the
#     round-1 1048B packet truncated 20.96ns -> 20ns (+4.8% rate error @400G).
#   - single-flow probe 8MiB (1MiB left the ACK tail = 35% of FCT at 400G).
#   - every cell emits qlen_ts.csv (aggregate cross-switch queue timeseries,
#     new observation-only key) so the burst check can sum the multi-tier
#     backlog instead of watching one link.
import io
import os
import re
import sys

SRC = '/work/simulation/experiment/scheme1_sba'
V2 = '/work/v2_400g'
CF = V2 + '/configs'
RS = V2 + '/results'
for d in (CF, RS, V2 + '/logs', V2 + '/reports'):
    os.path.isdir(d) or os.makedirs(d)

RATES = {10: '10Gbps', 200: '200Gbps', 400: '400Gbps'}
FANIN = 64
PKT_WIRE, PKT_PAY = 1000.0, 952.0   # wire=1000B: 800/40/20ns exact


def gbps(r):
    return r * 1e9


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def put(rel, text):
    p = os.path.join(V2, rel)
    d = os.path.dirname(p)
    os.path.isdir(d) or os.makedirs(d)
    io.open(p, 'w', encoding='utf-8', errors='surrogateescape').write(text)
    return p


# ---- per-rate scenario files -----------------------------------------------
def topo(rate):
    t = load(os.path.join(SRC, 'topology.txt')).replace('10Gbps', RATES[rate])
    return put('configs/topo_%dg.txt' % rate, t)


def flow_files(rate, size_bytes, stop_s, tag, start_s=0.05,
               release_ns=100000000, fanin=None):
    fanin = fanin or FANIN
    C = gbps(rate)
    bg_bytes = int(1.2 * 0.95 * C * stop_s / 8)      # never completes
    fl = ['%d' % (fanin + 1), '65 64 3 100 %d 0.002' % bg_bytes]
    for s in range(fanin):
        fl.append('%d 64 3 100 %d %.3f' % (s, size_bytes, start_s))
    put('configs/%s_flow.txt' % tag, '\n'.join(fl) + '\n')
    sch = ['%d' % (fanin + 1),
           '0 0 0 1 %d 0 0 0 10000000' % bg_bytes]
    for i in range(fanin):
        sch.append('%d 0 1 %d %d 0 0 0 %d' % (1 + i, fanin,
                                              size_bytes, release_ns))
    put('configs/%s_sched.txt' % tag, '\n'.join(sch) + '\n')
    put('configs/%s_link.txt' % tag,
        '1\n0 84 1 %d 400000 0 1\n' % int(C))
    pth = ['%d' % (fanin + 1)]
    for i in range(fanin + 1):
        pth.append('%d 1 0' % i)
    put('configs/%s_path.txt' % tag, '\n'.join(pth) + '\n')


def base_config(kind):
    return load(os.path.join(SRC, {
        'cbap': 'scr8_b040.txt',
        'dcqcn': 'mx_s3_dcqcn.txt',
        'hpcc': 'mx_s3_hpcc.txt',
        'dctcp': 'mx_s3_dctcp.txt',
        'timely': 'mx_s3_timely.txt',
    }[kind]))


def setkey(t, k, v):
    pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
    if pat.search(t):
        return pat.sub('%s %s' % (k, v), t)
    return t.rstrip('\n') + '\n%s %s\n' % (k, v)


def delkey(t, k):
    return re.sub(r'^%s\s+.*\n' % re.escape(k), '', t, flags=re.M)


def make_cell(tag, kind, rate, size_bytes, stop_s, over, heff_us,
              d_target_us=16, d_abs_us=80, bmax=0.04, buffer_mb=64,
              bg_frac=0.8, epoch_us=5, wire_domain=1, start_s=0.05,
              release_ns=100000000, fanin=None):
    fanin = fanin or FANIN
    C = gbps(rate)
    flow_files(rate, size_bytes, stop_s, tag, start_s, release_ns, fanin)
    t = base_config(kind)
    out = RS + '/' + tag
    os.path.isdir(out) or os.makedirs(out)
    old = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M).group(1)
    t = t.replace(old + '/', out + '/').replace(old, out)
    q_abs_B = min(C * d_abs_us * 1e-6 / 8.0, 0.25 * buffer_mb * 1048576)
    d_abs_eff_us = q_abs_B * 8.0 / C * 1e6
    kv = {
        'TOPOLOGY_FILE': topo(rate),
        'FLOW_FILE': CF + '/%s_flow.txt' % tag,
        'ROUND_SCHEDULE_FILE': CF + '/%s_sched.txt' % tag,
        'CBAP_LINK_FILE': CF + '/%s_link.txt' % tag,
        'CBAP_PATH_FILE': CF + '/%s_path.txt' % tag,
        'SIMULATOR_STOP_TIME': '%.3f' % stop_s,
        'QLEN_MON_START': '0', 'QLEN_MON_END': '%d' % int(stop_s * 1e9),
        'QLEN_MON_FILE': '/dev/null',
        'SCENARIO': tag,
        'APP_RATE_CAP_BPS': '%d' % int(bg_frac * C),
        'BUFFER_SIZE': '%d' % buffer_mb,
        'MIN_RATE': '%dMb/s' % int(0.01 * rate * 1000),
        'KMIN_MAP': '1 %d 400' % int(C),
        'KMAX_MAP': '1 %d 1600' % int(C),
        'PMAX_MAP': '1 %d 0.2' % int(C),
        'FINAL_COLLECTIVE_FLOW_COUNT': '%d' % fanin,
        'SBA_WIRE_DOMAIN_PLANNING': '%d' % wire_domain,
        'PACKET_PAYLOAD_SIZE': '952',
        'QLEN_TS_FILE': out + '/qlen_ts.csv',
        'QLEN_TS_INTERVAL_NS': '2000',
        'TX_TIME_ROUND_NS': '1',
    }
    if kind == 'cbap':
        kv.update({
            'CBAP_TX_RECORDS_MAX': '2000000',
            'CBAP_QC_H_GUARD_US': '%.3f' % heff_us,
            'CBAP_QC_APP_HARD_DELAY_US': '%.4f' % d_abs_eff_us,
            'CBAP_QC_SAFETY_MARGIN_BYTES': '%d' % (fanin * 1000),
            'CBAP_CONTROL_EPOCH_US': '%d' % epoch_us,
            'CBAP_ACTUATION_FILE': out + '/actuation.csv',
        })
        if bmax > 0:
            kv.update({
                'CBAP_QB2_BMAX_RATIO': '%.3f' % bmax,
                'CBAP_QB2_QTARGET_RATIO': '%.6f' %
                    (d_target_us / d_abs_eff_us),
                'CBAP_QB2_TRACE_FILE': out + '/controller_v2_trace.csv',
            })
        else:
            # boost-off ablation: the config validator (correctly) rejects
            # BMAX outside (0, 0.10], so the sanctioned switch is the v2
            # enable flag; the base config's BMAX stays and is inert.
            kv['CBAP_QUEUE_BAND_V2_ENABLE'] = '0'
    for k, v in over.items():
        kv[k] = v
    for k, v in kv.items():
        t = setkey(t, k, str(v))
    for k in ('CBAP_QC_TRACE_FILE', 'TX_SERIALIZATION_TRACE_FILE'):
        if k not in over:
            t = delkey(t, k)
    put('configs/%s.txt' % tag, t)
    print('cell %-22s rate=%dG size=%s stop=%.3fs Qabs=%.0fB(%.1fus) '
          'kind=%s' % (tag, rate, size_bytes, stop_s, q_abs_B, d_abs_eff_us,
                       kind))


MODE = sys.argv[1] if len(sys.argv) > 1 else 'preflight'
MB = 1048576
PROBE = 8 * MB   # single-flow probe: serialization >> RTT tail at 400G


def hg400():
    # measured H_eff (p99 of first_affected_at_bottleneck, ceil) written by
    # the overnight script after the heff_400g re-measurement; 13us is the
    # round-3 value used as fallback.
    p = V2 + '/reports/HG400_US'
    try:
        return float(io.open(p).read().strip())
    except (IOError, ValueError):
        return 13.0

if MODE == 'preflight':
    for rate in (10, 200, 400):
        C = gbps(rate)
        # single flow, no bg, no congestion; TX serialization ON to verify
        # the packet gap; theory time printed for the analyzer
        tag = 'pf_single_%dg' % rate
        stop = 0.05 + PROBE * 8.0 * (PKT_WIRE / PKT_PAY) / C * 3
        flow_files(rate, PROBE, stop, tag)
        # rewrite flow file: single flow only, no bg
        put('configs/%s_flow.txt' % tag, '1\n0 64 3 100 %d 0.01\n' % PROBE)
        put('configs/%s_sched.txt' % tag,
            '1\n0 0 0 1 %d 0 0 0 20000000\n' % PROBE)
        put('configs/%s_path.txt' % tag, '1\n0 1 0\n')
        t = base_config('dcqcn')
        out = RS + '/' + tag
        os.path.isdir(out) or os.makedirs(out)
        old = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M).group(1)
        t = t.replace(old + '/', out + '/').replace(old, out)
        for k, v in {
                'TOPOLOGY_FILE': topo(rate),
                'FLOW_FILE': CF + '/%s_flow.txt' % tag,
                'ROUND_SCHEDULE_FILE': CF + '/%s_sched.txt' % tag,
                'CBAP_LINK_FILE': CF + '/%s_link.txt' % tag,
                'CBAP_PATH_FILE': CF + '/%s_path.txt' % tag,
                'SIMULATOR_STOP_TIME': '%.3f' % stop,
                'QLEN_MON_START': '0',
                'QLEN_MON_END': '%d' % int(stop * 1e9),
                'QLEN_MON_FILE': '/dev/null', 'SCENARIO': tag,
                'APP_RATE_CAP_FLOW': '255',
                'BUFFER_SIZE': '64',
                'KMIN_MAP': '1 %d 400' % int(C),
                'KMAX_MAP': '1 %d 1600' % int(C),
                'PMAX_MAP': '1 %d 0.2' % int(C),
                'FINAL_COLLECTIVE_FLOW_COUNT': '1',
                'PACKET_PAYLOAD_SIZE': '952',
                'TX_TIME_ROUND_NS': '1',
                'TX_SERIALIZATION_TRACE_FILE':
                    out + '/tx_serialization.csv'}.items():
            t = setkey(t, k, str(v))
        t = delkey(t, 'CBAP_QC_TRACE_FILE')
        put('configs/%s.txt' % tag, t)
        print('cell %-22s single-flow line-rate check, stop=%.3fs'
              % (tag, stop))
        # 64-way sync burst, CC inert (KMIN >> buffer), bg 0.8C
        tag = 'pf_burst_%dg' % rate
        batch_s = FANIN * 262144 * 8.0 * (PKT_WIRE / PKT_PAY) / C
        stop = 0.1 + batch_s * 5 + 0.03
        make_cell(tag, 'dcqcn', rate, 262144, stop,
                  {'KMIN_MAP': '1 %d 999999999' % int(C),
                   'KMAX_MAP': '1 %d 1999999999' % int(C)}, heff_us=175)
elif MODE == 'heff':
    prov = {10: 175.0, 200: 40.0, 400: 40.0}   # PROVISIONAL guards, labelled
    for rate in (10, 200, 400):
        C = gbps(rate)
        batch_s = FANIN * 262144 * 8.0 * (PKT_WIRE / PKT_PAY) / C
        stop = 0.1 + batch_s * 5 + 0.03
        make_cell('heff_%dg' % rate, 'cbap', rate, 262144, stop, {},
                  heff_us=prov[rate])
    print('NOTE: H_GUARD values above are PROVISIONAL placeholders for the')
    print('measurement run only; the measured H_eff replaces them before')
    print('any screening cell is generated.')
elif MODE == 'screening':
    # 400G CBAP screening (preflight round-3 PASS, H_eff confirmed):
    #   D_target {8,16,32}us x BMAX {0.02,0.04,0.06}, D_abs=80us,
    #   H_GUARD = measured p99 rounded up = 13us at 400G.
    # Message 4MiB (~7x the 604KB BDP) so the queue-control regime engages;
    # 256KiB would be message-limited per the round-2/3 burst finding.
    # Warmup compressed: telemetry stabilizes in ~1ms (heff traces), so the
    # incast releases at 30ms instead of 100ms (bg release stays 10ms).
    # Compressed timeline (evidence-based): telemetry stabilizes in ~1ms,
    # the 4MiB batch drains in ~5.9ms, bg recovery is us-scale.  bg release
    # 10ms, incast ready 15ms / release 20ms, 14ms post-batch tail.
    # Cross design through the round-1 candidate (user trimmed the budget;
    # round-1 data showed d16/d32 rows byte-near-identical and b060 never
    # competitive, so the full grid is redundant):
    #   D_target axis @ BMAX=0.02 : 2, 4, 8, 16 us
    #   BMAX axis @ D_target=8us  : 0 (ablation), 0.01, 0.02, 0.04
    #   diagonal check            : d04_b010
    # Compressed timeline (evidence-based): telemetry stabilizes in ~1ms,
    # the 4MiB batch drains in ~5.9ms, bg recovery is us-scale.
    MSG = 4 * MB
    HG_400 = hg400()
    C = gbps(400)
    batch_s = FANIN * MSG * 8.0 * (PKT_WIRE / PKT_PAY) / C
    stop = 0.02 + batch_s + 0.014
    CROSS = [(2, 0.02), (4, 0.02), (8, 0.02), (16, 0.02),
             (8, 0.0), (8, 0.01), (8, 0.04), (4, 0.01)]
    for dt, bm in CROSS:
        tag = 'scrv2_d%02d_b%03d' % (dt, int(round(bm * 1000)))
        make_cell(tag, 'cbap', 400, MSG, stop, {}, heff_us=HG_400,
                  d_target_us=dt, bmax=bm, start_s=0.015,
                  release_ns=20000000)
    print('screening cross: 8 cells, H_GUARD=%.1fus stop=%.3fs'
          % (HG_400, stop))
elif MODE == 'screening_ext':
    print('screening_ext folded into the 8-cell cross (user trim); nothing '
          'to generate')
elif MODE == 'pilot':
    # Pilot matrix (user-approved): rates x sizes x arms.
    #   CBAP: screening winner D_target=8us BMAX=0.02, measured per-rate
    #         H_GUARD {10G:118, 200G:15, 400G: measured (12)}us
    #   HPCC: stock (INT-based; dimensionless knobs unchanged per spec)
    #   DCQCN x3 fairness arms:
    #     dcqs  stock          (v1 params verbatim: AI 50M, KMIN 400KB)
    #     dcqn  speed_normal   (AI=0.005C, HAI=0.01C; ECN KB unchanged)
    #     dcql  sn + low-ECN   (user: trade FCT/goodput for queue --
    #           delay-defined thresholds KMIN=2us, KMAX=8us of line rate)
    # Plus 400G buffer sweep {8,32}MB on 3 arms and one boost-off ablation.
    HG = {10: 118.0, 200: 15.0, 400: hg400()}
    SIZES = [('256k', 262144), ('1m', MB), ('4m', 4 * MB),
             ('16m', 16 * MB)]
    tags = []

    def pilot_cell(rate, sname, sbytes, arm, kind, over, buffer_mb=64,
                   bmax=0.02):
        C = gbps(rate)
        batch_s = FANIN * sbytes * 8.0 * (PKT_WIRE / PKT_PAY) / C
        stop = 0.02 + batch_s + 0.014
        tag = 'pv%dg_%s_%s' % (rate, sname, arm) + \
            ('' if buffer_mb == 64 else '_b%d' % buffer_mb)
        make_cell(tag, kind, rate, sbytes, stop, over, heff_us=HG[rate],
                  d_target_us=8, bmax=bmax, buffer_mb=buffer_mb,
                  start_s=0.015, release_ns=20000000)
        tags.append(tag)

    def dcqcn_arms(rate):
        C = gbps(rate)
        ai = max(1, int(round(0.005 * C / 1e6)))
        hai = max(1, int(round(0.01 * C / 1e6)))
        kmin_kb = max(3, int(round(C * 2e-6 / 8 / 1000)))
        kmax_kb = max(12, int(round(C * 8e-6 / 8 / 1000)))
        sn = {'RATE_AI': '%dMb/s' % ai, 'RATE_HAI': '%dMb/s' % hai}
        low = dict(sn)
        low['KMIN_MAP'] = '1 %d %d' % (int(C), kmin_kb)
        low['KMAX_MAP'] = '1 %d %d' % (int(C), kmax_kb)
        return [('dcqs', {}), ('dcqn', sn), ('dcql', low)]

    for rate in (10, 200, 400):
        for sname, sbytes in SIZES:
            pilot_cell(rate, sname, sbytes, 'cbap', 'cbap', {})
            pilot_cell(rate, sname, sbytes, 'hpcc', 'hpcc', {})
            for arm, over in dcqcn_arms(rate):
                pilot_cell(rate, sname, sbytes, arm, 'dcqcn', over)
    # 400G buffer sensitivity (default 64MB is in the main grid)
    for buf in (8, 32):
        pilot_cell(400, '4m', 4 * MB, 'cbap', 'cbap', {}, buffer_mb=buf)
        pilot_cell(400, '4m', 4 * MB, 'hpcc', 'hpcc', {}, buffer_mb=buf)
        for arm, over in dcqcn_arms(400):
            if arm == 'dcqn':
                pilot_cell(400, '4m', 4 * MB, arm, 'dcqcn', over,
                           buffer_mb=buf)
    # boost-off ablation at the headline point
    pilot_cell(400, '4m', 4 * MB, 'cbap0', 'cbap', {}, bmax=0.0)
    put('configs/PILOT_TAGS.txt', '\n'.join(tags) + '\n')
    print('pilot: %d cells (60 main + 6 buffer + 1 ablation), '
          'H_GUARD(400G)=%.1fus' % (len(tags), HG[400]))
elif MODE == 'matrix':
    # FORMAL MATRIX (user-approved design, reports/07):
    #   rule A: D_abs(rate) = max(80us, 7 x H_eff)  -> 826 / 105 / 84 us
    #   rule B: stop = release(20ms) + ideal_drain x 1.3 + 14ms tail
    # Frozen: CBAP d08_b020, H_GUARD measured per rate, epoch 5us,
    # MIN_RATE 0.01C, single seed.
    HG = {10: 118.0, 200: 15.0, 400: hg400()}
    DABS = {10: 826.0, 200: 105.0, 400: 84.0}
    SCEN = [('s0', 64, 262144, 0.8),
            ('s1', 64, MB, 0.8),
            ('s2', 64, 4 * MB, 0.8),
            ('s3', 64, 16 * MB, 0.8),
            ('s4', 64, 4 * MB, 0.95),
            ('s5', 32, 8 * MB, 0.8)]
    tags = []

    def dcqcn_arms(rate):
        C = gbps(rate)
        ai = max(1, int(round(0.005 * C / 1e6)))
        hai = max(1, int(round(0.01 * C / 1e6)))
        kmin_kb = max(3, int(round(C * 2e-6 / 8 / 1000)))
        kmax_kb = max(12, int(round(C * 8e-6 / 8 / 1000)))
        sn = {'RATE_AI': '%dMb/s' % ai, 'RATE_HAI': '%dMb/s' % hai}
        low = dict(sn)
        low['KMIN_MAP'] = '1 %d %d' % (int(C), kmin_kb)
        low['KMAX_MAP'] = '1 %d %d' % (int(C), kmax_kb)
        return sn, low

    def mx_cell(rate, scen, fanin, sbytes, bgf, arm, kind, over,
                buffer_mb=64, bmax=0.02):
        C = gbps(rate)
        batch_s = fanin * sbytes * 8.0 * (PKT_WIRE / PKT_PAY) / C
        stop = 0.02 + batch_s * 1.3 + 0.014
        tag = 'fm%dg_%s_%s' % (rate, scen, arm) + \
            ('' if buffer_mb == 64 else '_b%d' % buffer_mb)
        make_cell(tag, kind, rate, sbytes, stop, over, heff_us=HG[rate],
                  d_target_us=8, d_abs_us=DABS[rate], bmax=bmax,
                  buffer_mb=buffer_mb, bg_frac=bgf, start_s=0.015,
                  release_ns=20000000, fanin=fanin)
        tags.append(tag)

    for rate in (10, 200, 400):
        C = gbps(rate)
        sn, low = dcqcn_arms(rate)
        dctcp_sn = {'DCTCP_RATE_AI': '%dMb/s' % int(round(0.1 * C / 1e6))}
        for scen, fanin, sbytes, bgf in SCEN:
            mx_cell(rate, scen, fanin, sbytes, bgf, 'cbap', 'cbap', {})
            mx_cell(rate, scen, fanin, sbytes, bgf, 'hpcc', 'hpcc', {})
            mx_cell(rate, scen, fanin, sbytes, bgf, 'dcqn', 'dcqcn', sn)
            mx_cell(rate, scen, fanin, sbytes, bgf, 'dcql', 'dcqcn', low)
            mx_cell(rate, scen, fanin, sbytes, bgf, 'dctcp', 'dctcp',
                    dctcp_sn)
            mx_cell(rate, scen, fanin, sbytes, bgf, 'timely', 'timely', {})
        # annex: stock DCQCN (its high-rate collapse is a finding) and the
        # boost-off ablation, both at the headline scenario
        mx_cell(rate, 's2', 64, 4 * MB, 0.8, 'dcqs', 'dcqcn', {})
        mx_cell(rate, 's2', 64, 4 * MB, 0.8, 'cbap0', 'cbap', {}, bmax=0.0)
    # annex: 400G buffer sensitivity at the headline scenario
    sn400, _ = dcqcn_arms(400)
    for buf in (8, 32):
        mx_cell(400, 's2', 64, 4 * MB, 0.8, 'cbap', 'cbap', {},
                buffer_mb=buf)
        mx_cell(400, 's2', 64, 4 * MB, 0.8, 'hpcc', 'hpcc', {},
                buffer_mb=buf)
        mx_cell(400, 's2', 64, 4 * MB, 0.8, 'dcqn', 'dcqcn', sn400,
                buffer_mb=buf)
    put('configs/MATRIX_TAGS.txt', '\n'.join(tags) + '\n')
    print('formal matrix: %d cells (108 core + 6 annex arms + 6 buffer), '
          'H_GUARD=%s D_abs=%s' % (len(tags), HG, DABS))
elif MODE == 'frontier_ext':
    # Baseline queue-tight frontier EXTENSION (supplementary evidence, new
    # arm names, formal matrix untouched).  User request: push the
    # rate-for-queue tradeoff as low as practical.
    #   dcqx   = speed-normalized DCQCN + ultra-low delay-defined ECN
    #            (KMIN=0.5us, KMAX=2us of line rate, PMAX=1.0)
    #   dctcpx = speed-normalized DCTCP + the same ultra-low marking
    #   hpccx  = HPCC with U_TARGET 0.90 (its rate-for-queue knob; the
    #            0.90 point matches the v1 sweep precedent)
    #   timely has no config-exposed threshold (compile-time attributes)
    #   and is recorded as not adjustable.
    HG = {10: 118.0, 200: 15.0, 400: hg400()}
    DABS = {10: 826.0, 200: 105.0, 400: 84.0}
    SCEN = {'s0': (64, 262144, 0.8), 's1': (64, MB, 0.8),
            's2': (64, 4 * MB, 0.8), 's3': (64, 16 * MB, 0.8),
            's4': (64, 4 * MB, 0.95)}
    GROUPS = {10: ['s3'], 200: ['s0', 's1'],
              400: ['s0', 's1', 's2', 's4']}
    tags = []
    for rate, scens in sorted(GROUPS.items()):
        C = gbps(rate)
        kmin_kb = max(2, int(round(C * 0.5e-6 / 8 / 1000)))
        kmax_kb = max(6, int(round(C * 2e-6 / 8 / 1000)))
        ai = max(1, int(round(0.005 * C / 1e6)))
        hai = max(1, int(round(0.01 * C / 1e6)))
        lowmap = {'KMIN_MAP': '1 %d %d' % (int(C), kmin_kb),
                  'KMAX_MAP': '1 %d %d' % (int(C), kmax_kb),
                  'PMAX_MAP': '1 %d 1.0' % int(C)}
        dcqx = dict(lowmap)
        dcqx.update({'RATE_AI': '%dMb/s' % ai, 'RATE_HAI': '%dMb/s' % hai})
        dctcpx = dict(lowmap)
        dctcpx['DCTCP_RATE_AI'] = '%dMb/s' % int(round(0.1 * C / 1e6))
        hpccx = {'U_TARGET': '0.90'}
        for scen in scens:
            fanin, sbytes, bgf = SCEN[scen]
            batch_s = fanin * sbytes * 8.0 * (PKT_WIRE / PKT_PAY) / C
            stop = 0.02 + batch_s * 1.3 + 0.014
            for arm, kind, over in (('dcqx', 'dcqcn', dcqx),
                                    ('dctcpx', 'dctcp', dctcpx),
                                    ('hpccx', 'hpcc', hpccx)):
                tag = 'fx%dg_%s_%s' % (rate, scen, arm)
                make_cell(tag, kind, rate, sbytes, stop, over,
                          heff_us=HG[rate], d_target_us=8,
                          d_abs_us=DABS[rate], bg_frac=bgf, start_s=0.015,
                          release_ns=20000000, fanin=fanin)
                tags.append(tag)
    put('configs/FX_TAGS.txt', '\n'.join(tags) + '\n')
    print('frontier extension: %d cells (ECN KMIN=0.5us KMAX=2us PMAX=1.0; '
          'HPCC U_TARGET=0.90)' % len(tags))
else:
    print('mode %s not enabled this round (pilot gated on screening '
          'review)' % MODE)
    sys.exit(2)
print('%s cells generated under /work/v2_400g/' % MODE)
