# -*- coding: utf-8 -*-
# Register the stress round: zone coverage achieved under the official law,
# the quantified design envelope, and the honest relabel of the old abort.
import io

B = '/work/simulation/experiment/scheme1_sba'
doc = u'''# Zone-coverage stress round (st_2560 / st_2555 / st_2550) — 2026-08-20

Binary: occupancy-bound fix (fixAK) applied; byte regression reg_d3/reg_b040
vs frozen scr8 = 20/20 files identical (log: /work/stB_supervisor.log), so all
frozen CBAP results stand unchanged.

## Scenario
S3 base + second 64x1MiB batch (port 101) released into batch A's tail.
Infeasible-floor overlap: sum(MIN_RATE floors) = 13.5G > C = 10G while both
batches coexist -> queue grows at ~441 KB/ms with ZERO drain rights
(drainMax = C - floorSum < 0).  Probe variable = overlap duration.

## Results vs pre-registration
| cell | overlap | zones (ms, H/D/R) | queue max | over Q_abs | safety | verdict |
|---|---|---|---|---|---|---|
| st_2560 | ~1.0 ms | 4.58 / 2.31 / 32.47 | 1,022,848 B (97.5% Q_abs) | 0 | PFC/drop/retx 0, 128/128 | **PASS — full GREEN->HOLD->DRAIN->RED->GREEN arc, Q_abs held** |
| st_2555 | ~3.2 ms | 1.09 / 0.07 / 2.58 | 1,474,648 B (140.6%) | 199 | PFC/drop/retx 0, 128/128 | BOUNDARY_EXCEEDED (reclassified) |
| st_2550 | ~4.1 ms | 1.23 / 0.12 / 3.27 | 1,607,744 B (153.3%) | 261 | PFC/drop/retx 0, 128/128 | BOUNDARY_PROBE as pre-registered |

st_2560 additionally contained the documented Option-A residue (a ~4.6%
wire/payload over-commit in batch B's initial grants) for the whole batch:
RED forced-veto 6,493 epochs, lease-expiry reclaims 55, drain active 34.4 ms
at up to 3.18 G — the official b040 controller held the peak at 97.5% of
Q_abs.  This is the zone-coverage evidence for the paper; the shadow-threshold
diagnostic (old Option B) is unnecessary and was not run.

## Design envelope (quantified)
Feasible-floor overlap budget: T_max ~= (Q_red - Q_standing) * 8 /
(sum_floor_wire - C) ~= 2.2 ms for this configuration.  Inside it the zone
machinery holds Q_abs (st_2560); beyond it the violation is structural — no
controller action can drain below MIN_RATE floors — though PFC/drop/retx
remained 0 even at 153% of Q_abs (buffer headroom above Q_abs).

## Honest relabels / open items
1. The archived abort (st_2560_ADMISSION_FAILFAST_ON_INFEASIBLE_FLOORS.log)
   is RELABELED: the census proved the old fail-fast was a wire/payload
   domain artifact (margin independent of batch size; available ==
   C*1000/1048 exactly), NOT a designed floor-feasibility guard.  Evidence
   retained under the same filename; this note supersedes the old label.
2. OPEN (future work, not implemented per instruction): admission does not
   bound the infeasible-overlap DURATION, so overlaps beyond the envelope are
   now admitted and will exceed Q_abs (st_2555/st_2550).  A duration-budget
   admission check is the natural fix.
3. OPEN (Option B debt): grant budgets still mix wire/payload domains
   (~4.6%); the steady-state epoch controller is domain-correct and contains
   it.  A full domain unification would perturb all startup transients and
   requires a full re-run — deferred by decision.
'''
io.open(B + '/ZONE_COVERAGE_STRESS.md', 'w', encoding='utf-8').write(doc)
print('wrote ZONE_COVERAGE_STRESS.md')
