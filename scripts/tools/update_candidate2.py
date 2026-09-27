# -*- coding: utf-8 -*-
# Item 1: register the hold-out result as HELD_OUT_S4_S5_PASS (explicitly NOT
# GENERALIZES) with candidate/baseline gates separated, full per-scenario
# metrics, and the frozen no-retune rule.
import io

P = '/work/simulation/experiment/scheme1_sba/S3_TUNING_WINNER_CANDIDATE.md'
t = io.open(P, encoding='utf-8').read()
if 'HELD_OUT_S4_S5_PASS' in t:
    print('already appended')
else:
    t += u'''
## HELD_OUT_S4_S5_PASS (2026-08-19, single seed per scenario)

Label deliberately NOT "GENERALIZES": that term is reserved for
GENERALIZES_ACROSS_SEEDS after the multi-seed/perturbation stage.  b040 is
hereby FROZEN as the candidate configuration (BMAX=0.04C,
Q_target=0.025*Q_abs); no later held-out result may be used to swap the
winner or retune it.

### Gates, kept separate
- CANDIDATE gates (b040): PASS in S4 and S5 (all incast complete, PFC=0,
  drop=0, retx=0, qmax <= Q_abs, bg full & outside >= 99% of same-scenario D1).
- BASELINE observations (D1/DCQCN, report-only -- never absorbed into any
  aggregate PASS): violates Q_abs in BOTH scenarios: S4 15.90 ms over
  (qmax 1,276,464 B), S5 100.96 ms over (qmax 1,279,608 B).

### S4 (64x1MiB, bg cap 9.5G, stop 5.5 s)
| metric | D1 | D3 | b040 |
|---|---|---|---|
| CCT / BCT (ms) | 59.0692 / 59.0692 | 58.4925 / 58.4875 | 56.8446 / 56.8396 |
| FCT mean/p95/p99 (ms) | 54.33/58.12/58.45 | 58.44/58.45/58.45 | 56.79/56.81/56.81 |
| batch goodput (G) / util | 9.0888 / 0.909 | 9.1785 / 0.918 | 9.4445 / 0.944 |
| bg full / in-win / outside (G) | 7.1111 / 0.2001 / 7.2030 | 7.1111 / 0.1005 / 7.2034 | 7.1111 / 0.1011 / 7.2008 |
| bg recovery (ms) | 24.75 | 0.048 | 0.035 |
| queue mean/p95/p99/max (B) | 10140/0/410,792/1,276,464 | 16/0/0/12,576 | 230/0/17,816/28,296 |
| PFC / drop / retx | 0/0/0 | 0/0/0 | 0/0/0 |
| b040 vs D1 | CCT -3.77%, BCT -3.77%, p99 FCT -2.81% | | |

### S5 (64x4MiB, bg cap 8G, stop 6.0 s)
| metric | D1 | D3 | b040 |
|---|---|---|---|
| CCT / BCT (ms) | 230.3722 / 230.3722 | 233.9551 / 233.9501 | 227.2639 / 227.2589 |
| FCT mean/p95/p99 (ms) | 222.51/228.85/229.36 | 233.90/233.91/233.91 | 227.22/227.24/227.24 |
| batch goodput (G) / util | 9.3218 / 0.932 | 9.1790 / 0.918 | 9.4493 / 0.945 |
| bg full / in-win / outside (G) | 6.4000 / 0.1809 / 6.7004 | 6.4000 / 0.0965 / 6.7094 | 6.4000 / 0.0969 / 6.7001 |
| bg recovery (ms) | 20.93 | 0.045 | 0.036 |
| queue mean/p95/p99/max (B) | 38759/0/1,064,768/1,279,608 | 42/0/2,096/9,432 | 1176/0/37,728/48,208 |
| PFC / drop / retx | 0/0/0 | 0/0/0 | 0/0/0 |
| b040 vs D1 | CCT -1.35%, BCT -1.35%, p99 FCT -0.93% | | |

Notes carried forward:
- BCT and batch-goodput improvements are one effect (fixed batch bytes).
- D3 alone is scenario-dependent (-0.98% on S4, +1.56% on S5); the v2 top-up
  is the consistent-gain component.
- b040's controller stayed GREEN throughout both scenarios (HOLD/DRAIN/RED
  residence 0 ms); a dedicated stress cell is required before any claim about
  behaviour in the upper zones.
'''
    io.open(P, 'w', encoding='utf-8').write(t)
    print('appended HELD_OUT_S4_S5_PASS section')
