# -*- coding: utf-8 -*-
import io
B = '/work/simulation/experiment/scheme1_sba'
doc = u'''# Sensitivity annex (S3, 2026-08-22) — NEVER merged into the main matrix

Two disclosed variants, applied as labelled; nothing calibrated to any target.
CBAP control cells included in both groups.

## Group A — ENV_SENSITIVITY: BUFFER_SIZE 8 -> 2 MB (uniform, all 5 algos)

| algo | CCT delta | q_max | PFC pauses | retx |
|---|---|---|---|---|
| dcqcn | -0.65% | 1,279,608 -> 721,024 (PFC-clamped) | 0 -> 10,456 | 0 |
| dctcp | +1.56% | -> 721,024 | 0 -> 11,548 | 0 |
| timely | +0.41% | -> 712,800 | 0 -> 2,026 | 0 |
| hpcc | +0.01% | -> 712,860 | 0 -> 438 | 0 |
| cbapsba | 0.00% | 26,200 (unchanged) | 0 -> 0 | 0 |

Findings: on a shallow-buffer switch every baseline hits PFC (438-11,548
pause events inside ONE batch; queue clamped at the ~721 KB PFC threshold).
PFC being lossless, drops/retx stay 0 -- the deep-buffer main matrix hid the
pauses, not losses.  CBAP: zero PFC and 5/5 result files BYTE-IDENTICAL to
its standard-config matrix cell -- it does not depend on buffer depth.
Caveat stated: this is a single-hop bottleneck; in multi-hop fabrics PFC
storms additionally cause head-of-line blocking not measured here.

## Group B — ECN_SENSITIVITY: KMIN 400->100, KMAX 1600->400 (dcqcn/dctcp/cbap)

| algo | CCT | q_p99 | q_max | over Q_abs |
|---|---|---|---|---|
| dcqcn std | 58.3730 | 967,304 | 1,279,608 | 1,833 |
| dcqcn lowK | 59.5711 (+2.05%) | 254,664 | 1,250,264 | 62 |
| dctcp std | 57.2474 | 1,218,824 | 1,276,464 | 5,507 |
| dctcp lowK | 58.1910 (+1.65%) | 596,312 | 1,276,464 | 634 |
| cbapsba | 56.8412 (byte-identical either way) | 19,912 | 26,200 | 0 |

Findings: lowering ECN thresholds 4x buys the baselines lower steady-state
queues (p99 down 2-4x) at +1.7-2.1% completion time, and their RELEASE BURST
still peaks at ~1.25-1.28 MB over Q_abs -- reactive marking cannot act before
the burst arrives.  No ECN setting wins both axes: the lowK baselines are
BOTH slower than CBAP (gap grows to +4.8% / +2.4%) and still 13-30x above its
p99 queue.  CBAP's cells are byte-identical under either threshold set.

## Registration
- Group A cells: sx_a_* ; Group B cells: sx_b_* ; logs /work/sens_logs/.
- Pre-registered expectations (2026-08-21 approval) both confirmed; no
  further threshold lowering will be run in pursuit of any target gap.
'''
io.open(B + '/SENSITIVITY_ANNEX.md', 'w', encoding='utf-8').write(doc)
print('wrote SENSITIVITY_ANNEX.md')
