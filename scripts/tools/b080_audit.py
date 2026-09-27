# -*- coding: utf-8 -*-
# READ-ONLY root-cause audit of scr7_b080's ~0.01% boost duty.
# No simulation, no code change, no re-run.  Sources:
#   scr7_b080_out/controller_v2_trace.csv  (requested/effective/lease/veto/zone)
#   scr7_b080_out/qc_trace.csv             (boost_commanded, pending_generation)
#   scr7_b040_out/* (same pass, for the quantitative comparison only)
# Any answer a field cannot support is printed as TRACE_INSUFFICIENT, never
# guessed.
import csv
import os
import sys

B = '/work/simulation/experiment/scheme1_sba'
QTGT = 26214.0          # from the run's own #MANIFEST
QLOW, QHIGH, QRED, QABS = 524287.0, 915877.0, 981502.0, 1048574.0
HEFF_NS = 175000.0
C = 10.0e9


def load_v2(cell):
    p = os.path.join(B, '%s_out/controller_v2_trace.csv' % cell)
    rows = []
    with open(p) as fh:
        hdr = None
        for ln in fh:
            if ln.startswith('#'):
                continue
            w = ln.rstrip('\n').split(',')
            if hdr is None:
                hdr = {k: i for i, k in enumerate(w)}
                continue
            rows.append(w)
    return hdr, rows


def load_qc(cell):
    p = os.path.join(B, '%s_out/qc_trace.csv' % cell)
    out = {}
    with open(p) as fh:
        hdr = None
        for ln in fh:
            w = ln.rstrip('\n').split(',')
            if hdr is None:
                hdr = {k: i for i, k in enumerate(w)}
                continue
            # keyed by time_ns; keep boost_commanded + pending_generation
            try:
                out[int(w[hdr['time_ns']])] = (
                    float(w[hdr['boost_commanded']]),
                    float(w[hdr['pending_generation']]))
            except (ValueError, KeyError, IndexError):
                pass
    return out


def audit(cell):
    hdr, rows = load_v2(cell)
    need = ['time_ns', 'batch_active', 'queue_current_bytes',
            'queue_predicted_bytes', 'pending_excess_bytes',
            'arrival_wire_bps', 'service_wire_bps', 'boost_requested_bps',
            'boost_effective_bps', 'boost_lease_expire_ns', 'drain_bps',
            'aggregate_applied_bps', 'zone', 'veto_reason', 'generation']
    missing = [k for k in need if k not in hdr]
    if missing:
        print('%s: TRACE_INSUFFICIENT -- missing columns %s' % (cell, missing))
        return None
    qc = load_qc(cell)

    def g(w, k):
        try:
            return float(w[hdr[k]])
        except ValueError:
            return None

    T = lambda w: int(w[hdr['time_ns']])
    batch = [w for w in rows if w[hdr['batch_active']] == '1']
    if not batch:
        print('%s: TRACE_INSUFFICIENT -- no batch_active epochs' % cell)
        return None
    b0, b1 = T(batch[0]), T(batch[-1])
    print('=' * 74)
    print('%s : batch window %.6f -> %.6f s  (%d epochs)'
          % (cell, b0 / 1e9, b1 / 1e9, len(batch)))

    # ---- Q1: first occurrences -------------------------------------------
    def first(pred, seq, label):
        for w in seq:
            if pred(w):
                print('  first %-28s t=%.9f s' % (label, T(w) / 1e9))
                return T(w)
        print('  first %-28s NEVER' % label)
        return None

    print('--- Q1: first occurrences ---')
    t_req = first(lambda w: g(w, 'boost_requested_bps') > 0, rows,
                  'boost_requested > 0')
    t_cmd = None
    for tns in sorted(qc):
        if qc[tns][0] > 0:
            t_cmd = tns
            print('  first %-28s t=%.9f s (qc_trace)' %
                  ('boost_commanded > 0', tns / 1e9))
            break
    if t_cmd is None:
        print('  first %-28s NEVER (qc_trace)' % 'boost_commanded > 0')
    t_pex = first(lambda w: g(w, 'pending_excess_bytes') > 0, rows,
                  'pending_excess > 0')
    t_eff = first(lambda w: g(w, 'boost_effective_bps') > 0, rows,
                  'boost_effective > 0')
    if t_cmd and t_eff:
        print('  command -> effective delay    %.3f us (H_eff = %.3f us)'
              % ((t_eff - t_cmd) / 1e3, HEFF_NS / 1e3))

    # ---- Q2: what blocks the duty ----------------------------------------
    print('--- Q2: per-epoch blocking attribution (batch epochs only) ---')
    cls = dict(ON=0, LAW_ZERO_qpred_ge_target=0, WAITING_pending_eta=0,
               VETO_1_pred_over_qred=0, VETO_2_clamp=0, VETO_3_lease=0,
               VETO_5_red=0, ZONE_not_green=0, OTHER_zero=0)
    for w in batch:
        eff = g(w, 'boost_effective_bps')
        req = g(w, 'boost_requested_bps')
        v = w[hdr['veto_reason']]
        z = w[hdr['zone']]
        pend = qc.get(T(w), (0, 0))[1]
        if eff > 0:
            cls['ON'] += 1
        elif v == '1':
            cls['VETO_1_pred_over_qred'] += 1
        elif v == '3':
            cls['VETO_3_lease'] += 1
        elif v == '5':
            cls['VETO_5_red'] += 1
        elif z != 'GREEN':
            cls['ZONE_not_green'] += 1
        elif req == 0 and g(w, 'queue_predicted_bytes') >= QTGT:
            cls['LAW_ZERO_qpred_ge_target'] += 1
        elif pend > 0:
            cls['WAITING_pending_eta'] += 1
        elif v == '2':
            cls['VETO_2_clamp'] += 1
        else:
            cls['OTHER_zero'] += 1
    n = len(batch)
    for k in sorted(cls, key=lambda x: -cls[x]):
        if cls[k]:
            print('  %-28s %6d epochs  (%.2f%% of batch)'
                  % (k, cls[k], 100.0 * cls[k] / n))
    on = cls['ON']
    print('  duty inside batch             %.3f%%' % (100.0 * on / n))

    # ---- ON-period census + deposit check --------------------------------
    print('--- ON periods (lease bursts) ---')
    periods = []
    cur = None
    for w in rows:
        eff = g(w, 'boost_effective_bps')
        if eff > 0 and cur is None:
            cur = [T(w), T(w), eff, g(w, 'queue_current_bytes'), 0.0]
        elif eff > 0:
            cur[1] = T(w)
            cur[2] = max(cur[2], eff)
        elif cur is not None:
            cur[4] = g(w, 'queue_current_bytes')
            periods.append(cur)
            cur = None
    if cur is not None:
        periods.append(cur)
    for i, (s, e, mx, q_in, q_out) in enumerate(periods[:8]):
        dur = (e - s) / 1e3 + 5.0
        dep_pred = mx * (dur * 1e3) / 8.0 / 1e9 * 1e6   # bytes = bps*ns/8e9... compute plainly below
        dep_pred = mx * ((e - s) + 5000) / 8.0 / 1e9
        print('  #%d  %.6f -> %.6f s  dur=%.1f us  max=%.3f G  '
              'queue %.0f -> %.0f B  (predicted deposit ~%.0f B)'
              % (i + 1, s / 1e9, e / 1e9, dur, mx / 1e9,
                 q_in if q_in is not None else -1,
                 q_out if q_out is not None else -1, dep_pred))
    print('  total ON periods: %d' % len(periods))

    # ---- post-burst persistence: does Q_pred stay >= Q_target? -----------
    if periods:
        e_last = periods[0][1]
        after = [w for w in batch if T(w) > e_last]
        if after:
            above = sum(1 for w in after
                        if g(w, 'queue_predicted_bytes') >= QTGT)
            slack = [(g(w, 'service_wire_bps') or 0) -
                     (g(w, 'aggregate_applied_bps') or 0) for w in after]
            slack = [s for s in slack if s is not None]
            print('--- post-first-burst persistence ---')
            print('  batch epochs after burst #1   %d' % len(after))
            print('  of which Q_pred >= Q_target   %d  (%.2f%%)'
                  % (above, 100.0 * above / len(after)))
            print('  mean drain slack C - applied  %.4f Gbps'
                  % (sum(slack) / len(slack) / 1e9))

    # ---- consistency checks (B/C detectors) ------------------------------
    print('--- correctness checks ---')
    bad = 0
    # 1. effective while lease expired
    for w in rows:
        if g(w, 'boost_effective_bps') > 0 and \
                g(w, 'boost_lease_expire_ns') > 0 and \
                T(w) > g(w, 'boost_lease_expire_ns') + 5000:
            bad += 1
    print('  effective>0 past its lease    %d epochs %s'
          % (bad, '(VIOLATION)' if bad else '(ok)'))
    # 2. pending that never became effective within 2*H_eff
    stuck = 0
    pend_since = None
    for tns in sorted(qc):
        cmd, pend = qc[tns]
        if pend > 0 and pend_since is None:
            pend_since = tns
        elif pend == 0:
            pend_since = None
        elif pend_since and tns - pend_since > 2 * HEFF_NS:
            stuck += 1
            pend_since = None
    print('  pending stuck > 2*H_eff       %d %s'
          % (stuck, '(VIOLATION)' if stuck else '(ok)'))
    # 3. commanded in qc but never requested in v2
    cmd_epochs = sum(1 for tns in qc if qc[tns][0] > 0)
    req_epochs = sum(1 for w in rows if g(w, 'boost_requested_bps') > 0)
    print('  qc commanded epochs           %d' % cmd_epochs)
    print('  v2 requested epochs           %d' % req_epochs)
    return dict(cell=cell, batch=n, on=on, periods=len(periods),
                bad_lease=bad, stuck=stuck)


r080 = audit('scr7_b080')
r040 = audit('scr7_b040')

print('=' * 74)
print('--- Q4 verdict ---')
if not r080:
    print('TRACE_INSUFFICIENT')
    sys.exit(1)
# saturation arithmetic, printed so the verdict is checkable
for bm in (0.04, 0.08):
    dep = bm * C * HEFF_NS / 1e9 / 8.0
    print('  BMAX=%.2fC: one full lease deposits %.0f B against '
          'Q_target=%.0f B' % (bm, dep, QTGT))
print('  saturation bound: BMAX_sat = Q_target*8/H_eff = %.3f Gbps '
      '(= %.4f C) from an empty queue; lower once the queue is non-empty'
      % (QTGT * 8.0 / (HEFF_NS / 1e9) / 1e9,
         QTGT * 8.0 / (HEFF_NS / 1e9) / C))
