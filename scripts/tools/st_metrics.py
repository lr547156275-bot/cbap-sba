# -*- coding: utf-8 -*-
# Stress-cell analysis against the PRE-REGISTERED expectations.
#   st_2560 -> HOLD round-trip; st_2555 -> DRAIN; st_2550 -> RED boundary probe
# Acceptance (st_2560/st_2555): zones left GREEN and returned, drain>0 seen,
# queue <= Q_abs, PFC/drop/retx = 0, finite recovery, batch B completes, bg
# preserved.  st_2550 is a boundary probe: a transient Q_abs excursion there
# is documented as the infeasible-floor structural limit, never hidden.
import csv
import os

B = '/work/simulation/experiment/scheme1_sba'
Q_ABS = 1048575.0
NA, NB = 64, 64
CELLS = [('st_2560', 'HOLD round-trip expected'),
         ('st_2555', 'DRAIN engagement expected'),
         ('st_2550', 'RED boundary probe (Q_abs excursion = documented limit)')]


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


for tag, expect in CELLS:
    d = os.path.join(B, '%s_out' % tag)
    print('=' * 74)
    print('%s  [pre-registered: %s]' % (tag, expect))
    if not os.path.isfile(os.path.join(d, 'DONE')):
        print('  NOT_DONE')
        continue

    # ---- zones / boost / drain / veto from controller_v2_trace ------------
    vt = os.path.join(d, 'controller_v2_trace.csv')
    zres = {}
    drain_on = boost_on = 0
    veto = {}
    seq = []          # (t_ns, zone, q0) for excursion + recovery timing
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
                z = w[hdr['zone']]
                t = int(w[hdr['time_ns']])
                q0 = float(w[hdr['queue_current_bytes']])
                dr = float(w[hdr['drain_bps']])
                bo = float(w[hdr['boost_effective_bps']])
                v = w[hdr['veto_reason']]
            except (ValueError, IndexError):
                continue
            zres[z] = zres.get(z, 0) + 1
            if dr > 0:
                drain_on += 1
            if bo > 0:
                boost_on += 1
            if v not in ('0', ''):
                veto[v] = veto.get(v, 0) + 1
            if z != 'GREEN' or q0 > 100000:
                seq.append((t, z, q0))
    print('  zone residence (ms): %s' %
          ', '.join('%s=%.2f' % (z, zres.get(z, 0) * 5e-3)
                    for z in ('GREEN', 'HOLD', 'DRAIN', 'RED')))
    print('  drain>0 epochs: %d (%.2f ms)   boost>0 epochs: %d (%.2f ms)'
          % (drain_on, drain_on * 5e-3, boost_on, boost_on * 5e-3))
    print('  veto counts: %s' % (veto or '{}'))
    nong = [s for s in seq if s[1] != 'GREEN']
    if nong:
        t0, t1 = nong[0][0], nong[-1][0]
        print('  non-GREEN excursion: %.6f -> %.6f s  (recovery %.3f ms '
              'after last non-GREEN epoch)' % (t0 / 1e9, t1 / 1e9,
                                               (t1 - t0) / 1e6))
    else:
        print('  non-GREEN excursion: NONE (stayed GREEN)')

    # ---- queue peak vs bounds ---------------------------------------------
    ts = rd(os.path.join(d, 'selected_link_timeseries.csv'))
    q = [f(r, 'queue_bytes') for r in ts]
    q = [x for x in q if x is not None]
    qmax = max(q) if q else 0
    over = sum(1 for x in q if x > Q_ABS)
    print('  queue max: %.0f B (%.1f%% of Q_abs)   samples over Q_abs: %d'
          % (qmax, 100.0 * qmax / Q_ABS, over))

    # ---- batch A / B completion via flow ids ------------------------------
    ft = rd(os.path.join(d, 'flow_timing.csv'))
    la_a, la_b, na, nb = 0, 0, 0, 0
    for r in ft:
        try:
            fid = int(r['flow_id'])
        except (KeyError, ValueError):
            continue
        a = f(r, 'last_ack_ns')
        if a is None:
            continue
        if 1 <= fid <= NA:
            na += 1
            la_a = max(la_a, a)
        elif NA < fid <= NA + NB:
            nb += 1
            la_b = max(la_b, a)
    print('  batch A completed: %d/%d  last_ack %.6f s' % (na, NA, la_a / 1e9))
    print('  batch B completed: %d/%d  last_ack %.6f s' % (nb, NB, la_b / 1e9))

    # ---- safety ------------------------------------------------------------
    fs = rd(os.path.join(d, 'flow_summary.csv'))
    pf = rd(os.path.join(d, 'pfc_events.csv'))
    retx = sum(int(float(r.get('retx_events', 0) or 0)) for r in fs)
    bg = [r for r in fs if (f(r, 'total_size_bytes', 0) or 0) >= (1 << 30)]
    bga = f(bg[0], 'acked_bytes', 0) if bg else 0
    dr = 0
    log = '/work/stress_logs/%s.log' % tag
    if os.path.isfile(log):
        with open(log, errors='replace') as fh:
            for ln in fh:
                if 'Drop:' in ln:
                    dr += 1
    print('  PFC=%d drops=%d retx=%d   bg acked %.3f GB'
          % (len(pf), dr, retx, bga / 1e9))

    # ---- verdict against pre-registration ----------------------------------
    left_green = bool(nong)
    ok_abs = over == 0
    ok_safe = len(pf) == 0 and dr == 0 and retx == 0
    ok_done = na == NA and nb == NB
    if tag in ('st_2560', 'st_2555'):
        verdict = 'PASS' if (left_green and ok_abs and ok_safe and ok_done
                             and drain_on > 0) else 'CHECK'
        if not left_green:
            verdict = 'STAYED_GREEN (excursion did not materialise; ' \
                'pre-registered expectation not met -- report as-is)'
    else:
        verdict = 'BOUNDARY_PROBE: over_Q_abs=%d, PFC=%d -- documented ' \
            'structural-limit behaviour' % (over, len(pf))
    print('  VERDICT: %s' % verdict)
