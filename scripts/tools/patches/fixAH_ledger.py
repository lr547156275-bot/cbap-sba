# -*- coding: utf-8 -*-
# B080 root cause fix: LEDGER_GHOST_ARRIVAL (classification B/C, correctness).
#
# Two coupled defects, both in the per-QP command bookkeeping -- NOT in the
# frozen thresholds, zones, laws or checkers:
#
# 1. PROPAGATION (DeliverCbapPortSummary): the per-QP share is the ABSOLUTE
#    aggregate (boostCmd - drainCmd)/genSize but is applied RELATIVE to
#    senderEffective, which already contains the current boost.  A
#    down-to-zero command therefore computes share = 0, sets NEITHER pending
#    flag, and freezes commandedWireBps at the still-boosted senderEffective.
#    Fix: share = (commandedNet - effectiveNet)/genSize, the true delta.
#
# 2. CONFIRMATION (QueueControllerEpoch): once a command's deadline passes,
#    commandedWireBps is never cleared, so the confirmation branch re-asserts
#    predictedArrivalWireBps = commandedWireBps EVERY subsequent epoch,
#    overwriting the per-epoch refresh from the QP's actual rate.  Combined
#    with defect 1 this made a +0.8 G arrival ghost permanent (measured:
#    pending_excess locked at 26,528 B for 58 ms, p50 == p99).
#    Fix: clear commandedWireBps on confirmation; the entry then returns to
#    tracking the actual sender rate, and any ghost is bounded by H_eff.
#
# Evidence: b080_audit passes 1+2 (single 175 us burst, then LAW_ZERO for
# 99.08% of batch epochs with a CONSTANT envelope term that alone exceeds
# Q_target; zero vetoes; zero lease violations; zero same-generation stuck
# pendings).  b005-b040 carry the same ghost (b040: 15,901 B constant), below
# Q_target, so they functioned but their numbers are biased -> all seven S3
# cells must be re-run after this fix.
import io
import sys

HWC = '/work/simulation/src/point-to-point/model/rdma-hw.cc'
c = io.open(HWC, encoding='utf-8', errors='surrogateescape').read()

if 'commandedNet' in c:
    print('already applied')
    sys.exit(0)

edits = []


def E(tag, old, new):
    edits.append((tag, old, new))


E('share-delta',
  '\t\t\tconst uint32_t genSize = runtime.qcNewGenCount;\n'
  '\t\t\tconst long double share = genSize == 0 ? 0.0L :\n'
  '\t\t\t\t(long double)(runtime.qcBoostCommandedBps -\n'
  '\t\t\t\t\truntime.qcDrainCommandedBps) /\n'
  '\t\t\t\t(long double)genSize;',
  '\t\t\tconst uint32_t genSize = runtime.qcNewGenCount;\n'
  '\t\t\t// LEDGER_GHOST_ARRIVAL fix, defect 1: the share must be the DELTA\n'
  '\t\t\t// between the commanded and the currently effective aggregate,\n'
  '\t\t\t// because it is applied on top of senderEffective (which already\n'
  '\t\t\t// contains the effective boost).  Using the absolute commanded\n'
  '\t\t\t// value made a down-to-zero command compute share = 0: no pending\n'
  '\t\t\t// flag, and commandedWireBps frozen at the boosted rate.\n'
  '\t\t\tconst long double commandedNet =\n'
  '\t\t\t\t(long double)runtime.qcBoostCommandedBps -\n'
  '\t\t\t\t(long double)runtime.qcDrainCommandedBps;\n'
  '\t\t\tconst long double effectiveNet =\n'
  '\t\t\t\t(long double)runtime.qcBoostEffectiveBps -\n'
  '\t\t\t\t(long double)runtime.qcDrainTargetBps;\n'
  '\t\t\tconst long double share = genSize == 0 ? 0.0L :\n'
  '\t\t\t\t(commandedNet - effectiveNet) / (long double)genSize;')

E('confirm-clear',
  '\t\tif (nowNs >= it->second.effectDeadlineNs) {\n'
  '\t\t\tit->second.oldWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.senderEffectiveWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.predictedArrivalWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.pendingUp = false;\n'
  '\t\t\tit->second.pendingDown = false;\n'
  '\t\t}',
  '\t\tif (nowNs >= it->second.effectDeadlineNs) {\n'
  '\t\t\tit->second.oldWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.senderEffectiveWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.predictedArrivalWireBps = it->second.commandedWireBps;\n'
  '\t\t\tit->second.pendingUp = false;\n'
  '\t\t\tit->second.pendingDown = false;\n'
  '\t\t\t// LEDGER_GHOST_ARRIVAL fix, defect 2: a confirmed command is\n'
  '\t\t\t// CLOSED.  Leaving commandedWireBps set made this branch re-assert\n'
  '\t\t\t// the stale value into predictedArrivalWireBps every epoch,\n'
  '\t\t\t// overwriting the refresh from the actual sender rate and keeping\n'
  '\t\t\t// a boost-era arrival ghost alive indefinitely.  Cleared, the\n'
  '\t\t\t// entry falls through the inactive guard above and tracks reality.\n'
  '\t\t\tit->second.commandedWireBps = 0;\n'
  '\t\t}')

bad = 0
for tag, old, new in edits:
    n = c.count(old)
    print('%-15s count=%d %s' % (tag, n, 'OK' if n == 1 else 'FAIL'))
    if n != 1:
        bad += 1
if bad:
    print('ANCHOR FAIL -- nothing written')
    sys.exit(2)
for tag, old, new in edits:
    c = c.replace(old, new, 1)
io.open(HWC, 'w', encoding='utf-8', errors='surrogateescape').write(c)
print('ledger fix applied atomically (2 edits, rdma-hw.cc only)')
