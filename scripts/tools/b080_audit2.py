# -*- coding: utf-8 -*-
# READ-ONLY audit pass 2: the three items pass 1 left open.
#  (a) Q3 trajectory, epoch by epoch, around the single b080 burst.
#  (b) generation-aware pending check: pass 1's ">2*H_eff" detector counted
#      legal downward-replacement chains (each replacement restarts the ETA)
#      as "stuck".  A real violation is the SAME generation pending > H_eff+2
#      epochs.
#  (c) decomposition of Q_pred in the LAW_ZERO epochs: physical queue vs
#      pending-envelope; plus where b080's 0.2832 G "drain slack" comes from
#      (batch-tail demand decay vs mid-batch underfill), via batch thirds.
import csv
import os

B = '/work/simulation/experiment/scheme1_sba'
QTGT = 26214.0
HEFF_NS = 175000.0


def load_v2(cell):
    p = os.path.join(B, '%s_out/controller_v2_trace.csv' % cell)
    rows = []
    hdr = None
    with open(p) as fh:
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
    hdr = None
    with open(p) as fh:
        for ln in fh:
            w = ln.rstrip('\n').split(',')
            if hdr is None:
                hdr = {k: i for i, k in enumerate(w)}
                continue
            try:
                out[int(w[hdr['time_ns']])] = (
                    float(w[hdr['boost_commanded']]),
                    int(float(w[hdr['pending_generation']])))
            except (ValueError, KeyError, IndexError):
                pass
    return out


def stats(v):
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    return (sum(s) / n, s[n // 2], s[int((n - 1) * 0.99)])


import sys
PFX = sys.argv[1] if len(sys.argv) > 1 else 'scr7'
for cell in ('%s_b080' % PFX, '%s_b040' % PFX):
    hdr, rows = load_v2(cell)
    qc = load_qc(cell)

    def g(w, k):
        try:
            return float(w[hdr[k]])
        except ValueError:
            return 0.0

    T = lambda w: int(w[hdr['time_ns']])
    batch = [w for w in rows if w[hdr['batch_active']] == '1']
    b0, b1 = T(batch[0]), T(batch[-1])
    print('=' * 76)
    print('%s' % cell)

    # ---- (b) generation-aware pending check ------------------------------
    stuck_same_gen = 0
    chains = 0
    chain_max_len_ns = 0
    gen_since = {}
    prev_pend = 0
    chain_start = None
    for tns in sorted(qc):
        cmd, gen = qc[tns]
        if gen > 0:
            if gen not in gen_since:
                gen_since[gen] = tns
            elif tns - gen_since[gen] > HEFF_NS + 10000:
                stuck_same_gen += 1
                del gen_since[gen]
            if prev_pend == 0:
                chain_start = tns
        else:
            if prev_pend > 0 and chain_start is not None:
                chains += 1
                if tns - chain_start > chain_max_len_ns:
                    chain_max_len_ns = tns - chain_start
                chain_start = None
        prev_pend = gen
    print('--- (b) pending, generation-aware ---')
    print('  SAME generation pending > H_eff+2ep : %d  %s'
          % (stuck_same_gen,
             '(REAL VIOLATION)' if stuck_same_gen else '(none: pass-1 "96" '
             'was legal replacement chains, a detector artifact)'))
    print('  replacement chains                  : %d, longest %.0f us'
          % (chains, chain_max_len_ns / 1e3))

    # ---- (c) LAW_ZERO decomposition + batch thirds ------------------------
    lawzero_q0, lawzero_pex = [], []
    thirds = [[], [], []]
    for w in batch:
        qp = g(w, 'queue_predicted_bytes')
        if g(w, 'boost_requested_bps') == 0 and qp >= QTGT:
            lawzero_q0.append(g(w, 'queue_current_bytes'))
            lawzero_pex.append(g(w, 'pending_excess_bytes'))
        idx = min(2, 3 * (T(w) - b0) // max(1, (b1 - b0)))
        thirds[idx].append((g(w, 'aggregate_applied_bps'),
                            g(w, 'queue_current_bytes'),
                            g(w, 'pending_excess_bytes')))
    print('--- (c) LAW_ZERO epochs: what holds Q_pred >= Q_target ---')
    for name, v in (('queue_current', lawzero_q0),
                    ('pending_excess', lawzero_pex)):
        st = stats(v)
        if st:
            print('  %-16s mean=%8.0f  p50=%8.0f  p99=%8.0f  (n=%d)'
                  % (name, st[0], st[1], st[2], len(v)))
    print('--- batch thirds: applied sum / queue / pending_excess ---')
    for i, th in enumerate(thirds):
        if not th:
            continue
        ap = stats([x[0] for x in th])
        qq = stats([x[1] for x in th])
        px = stats([x[2] for x in th])
        print('  third %d: applied mean=%.4f G  queue mean=%6.0f B  '
              'pending_excess mean=%6.0f B'
              % (i + 1, ap[0] / 1e9, qq[0], px[0]))

    # ---- (a) Q3 trajectory (b080 only, around the single burst) ----------
    if cell == 'scr7_b080':
        print('--- (a) Q3 trajectory 2.000010 -> 2.000450 s ---')
        print('  %-11s %-6s %8s %8s %8s %7s %7s %7s %7s %12s %5s %4s'
              % ('t(s)', 'zone', 'q0', 'q_pred', 'pendexc', 'req(G)',
                 'cmd(G)', 'eff(G)', 'drn(G)', 'lease_us_lft', 'gen',
                 'veto'))
        for w in rows:
            tns = T(w)
            if tns < 2000010000 or tns > 2000450000:
                continue
            cmd, gen = qc.get(tns, (0.0, 0))
            lease = g(w, 'boost_lease_expire_ns')
            left = (lease - tns) / 1e3 if lease > tns else 0.0
            print('  %.9f %-6s %8.0f %8.0f %8.0f %7.3f %7.3f %7.3f %7.3f '
                  '%12.1f %5d %4s'
                  % (tns / 1e9, w[hdr['zone']],
                     g(w, 'queue_current_bytes'),
                     g(w, 'queue_predicted_bytes'),
                     g(w, 'pending_excess_bytes'),
                     g(w, 'boost_requested_bps') / 1e9, cmd / 1e9,
                     g(w, 'boost_effective_bps') / 1e9,
                     g(w, 'drain_bps') / 1e9, left, gen,
                     w[hdr['veto_reason']]))
