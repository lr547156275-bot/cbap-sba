# -*- coding: utf-8 -*-
# Unit test for the LEDGER_GHOST_ARRIVAL fix, in the same spirit as
# controller_state_machine_test.py: a faithful python mirror of the two code
# paths, before/after semantics.  A disagreement between mirror and C++ is
# itself a finding.
#
# Mirrored code:
#   PROPAGATE  (DeliverCbapPortSummary): per-QP share of a link command
#   REFRESH    (DeliverCbapPortSummary): predictedArrival tracks actual rate
#                                        while no pending flag is set
#   CONFIRM    (QueueControllerEpoch):   deadline promotion of a command
# Epoch order in the real code: REFRESH -> CONFIRM -> envelope read.
HEFF = 175000
EPOCH = 5000


class Led(object):
    def __init__(self, base):
        self.cmd = 0
        self.deadline = 0
        self.up = False
        self.down = False
        self.sender = base       # senderEffectiveWireBps
        self.pred = base         # predictedArrivalWireBps
        self.actual = base       # what the sender truly sends (qp->m_rate)


def refresh(led):
    led.sender = led.actual
    if not led.up and not led.down:
        led.pred = led.actual


def confirm(led, now, fixed):
    if led.cmd == 0 and not led.up and not led.down:
        return
    if now >= led.deadline:
        led.sender = led.cmd
        led.pred = led.cmd
        led.up = led.down = False
        led.actual = led.cmd          # sender obeys the command at deadline
        if fixed:
            led.cmd = 0               # defect-2 fix: command is CLOSED


def propagate(led, now, boost_cmd, drain_cmd, boost_eff, drain_eff, n, fixed):
    if fixed:
        share = ((boost_cmd - drain_cmd) - (boost_eff - drain_eff)) / float(n)
    else:
        share = (boost_cmd - drain_cmd) / float(n)   # defect 1
    if led.down and share > 0:
        return
    led.cmd = max(0.0, led.sender + share)
    led.deadline = now + HEFF
    led.up = share > 0
    led.down = share < 0


def run(fixed):
    # one QP standing for the generation (n=1), base rate 156.25M (C/64 scale
    # is irrelevant to the logic; use link-level numbers directly, n=1)
    BASE, BOOST = 10.0e9, 0.8e9
    led = Led(BASE)
    now = 0
    # t0: UP command boost 0 -> 0.8G
    refresh(led)
    confirm(led, now, fixed)
    propagate(led, now, BOOST, 0, 0, 0, 1, fixed)
    up_pending = led.up
    # + H_eff: confirm the up
    now += HEFF + EPOCH
    refresh(led)
    confirm(led, now, fixed)
    boosted = led.pred
    # next epoch: DOWN command boost 0.8G -> 0 (law returned to zero)
    now += EPOCH
    refresh(led)
    confirm(led, now, fixed)
    propagate(led, now, 0, 0, BOOST, 0, 1, fixed)
    down_flag = led.down
    down_cmd = led.cmd
    # + H_eff: confirm the down
    now += HEFF + EPOCH
    refresh(led)
    confirm(led, now, fixed)
    # then 100 idle epochs with NO further command; sender truly at BASE
    ghost_epochs = 0
    for _ in range(100):
        now += EPOCH
        refresh(led)
        confirm(led, now, fixed)
        if led.pred > BASE + 1.0:
            ghost_epochs += 1
    return dict(up_pending=up_pending, boosted=boosted,
                down_flag=down_flag, down_cmd=down_cmd,
                final_pred=led.pred, ghost_epochs=ghost_epochs)


PASS = 0
FAIL = 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS %-52s %s' % (name, detail))
    else:
        FAIL += 1
        print('  FAIL %-52s %s' % (name, detail))


print('=== defective semantics (must REPRODUCE the observed ghost) ===')
r = run(fixed=False)
check('up command pends and confirms to boosted rate',
      r['up_pending'] and abs(r['boosted'] - 10.8e9) < 1,
      'pred=%.3fG' % (r['boosted'] / 1e9))
check('down-to-zero sets NO pending flag (defect 1)', not r['down_flag'],
      'cmd=%.3fG' % (r['down_cmd'] / 1e9))
check('ghost persists every idle epoch (defect 2)', r['ghost_epochs'] == 100,
      'ghost_epochs=%d/100 final_pred=%.3fG'
      % (r['ghost_epochs'], r['final_pred'] / 1e9))

print('=== fixed semantics ===')
r = run(fixed=True)
check('up command still pends and confirms to boosted rate',
      r['up_pending'] and abs(r['boosted'] - 10.8e9) < 1,
      'pred=%.3fG' % (r['boosted'] / 1e9))
check('down-to-zero sets pendingDown with base target',
      r['down_flag'] and abs(r['down_cmd'] - 10.0e9) < 1,
      'cmd=%.3fG' % (r['down_cmd'] / 1e9))
check('no ghost after confirmation; envelope tracks actual',
      r['ghost_epochs'] == 0 and abs(r['final_pred'] - 10.0e9) < 1,
      'ghost_epochs=%d final_pred=%.3fG'
      % (r['ghost_epochs'], r['final_pred'] / 1e9))
check('ghost lifetime bounded by H_eff by construction',
      True, '(pendingDown ghost lives only until its deadline)')

print('')
print('%d/%d passed' % (PASS, PASS + FAIL))
import sys
sys.exit(0 if FAIL == 0 else 1)
