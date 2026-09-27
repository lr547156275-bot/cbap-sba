# -*- coding: utf-8 -*-
# Append the post-fix scr8 record to S3_TUNING_WINNER_CANDIDATE.md.
import io

P = '/work/simulation/experiment/scheme1_sba/S3_TUNING_WINNER_CANDIDATE.md'
t = io.open(P, encoding='utf-8').read()
if 'scr8 post-fix record' in t:
    print('already appended')
else:
    t += u'''
## scr8 post-fix record (SUPERSEDES the scr7 table above)

Ledger fix verified: 16/16 D1/D3 result files byte-identical to scr7; ghost
eliminated (b080 LAW_ZERO 11,615 -> 161 epochs; pending_excess no longer a
constant).  Post-fix landscape:

| arm | CCT (ms) | vs D1 | batch goodput (G) | queue p99/max (B) | gates |
|---|---|---|---|---|---|
| scr8_d1 | 58.3730 | - | 9.1972 | 967,304 / 1,279,608 | FAIL (qmax>Q_abs, baseline) |
| scr8_d3 | 58.4911 | TIE (+0.20%) | 9.1787 | 1,048 / 9,432 | PASS |
| scr8_b005 | 58.2011 | TIE (-0.29%) | 9.2244 | 1,048 / 11,528 | PASS |
| scr8_b010 | 58.2367 | TIE (-0.23%) | 9.2188 | 1,048 / 13,624 | PASS |
| scr8_b020 | 58.2217 | TIE (-0.26%) | 9.2212 | 1,048 / 15,720 | PASS |
| **scr8_b040** | **56.8412** | **-2.62%** | **9.4451** | 19,912 / 26,200 | PASS |
| scr8_b080 | 58.4757 | TIE (+0.18%) | 9.1811 | 2,096 / 29,344 | PASS |

Honesty notes carried into any later use of this table:
- scr7's apparent b010/b020 gains (-0.78%/-1.75%) were LEDGER_GHOST artifacts
  and DISAPPEAR after the fix; the scr7 v2 columns must not be cited.
- The post-fix landscape is a LONE SPIKE at BMAX=0.04C (all other doses TIE).
  Non-smooth response on one deterministic seed+scenario is an overfit /
  resonance warning; b040 is therefore a CANDIDATE pending S4/S5 hold-out.
- Mechanism hypothesis (unproven, from scr8 audit): b040 sustains a
  17.5-22.3 KB standing queue for the whole batch at applied ~= 10.0 G (full
  cap, no idle gaps); b080 still shows an UNEXPLAINED ~0.28 G applied
  underfill (9.70-9.74 G across all batch thirds) and cannot hold a deposit.
  Open items, not conclusions.
'''
    io.open(P, 'w', encoding='utf-8').write(t)
    print('appended scr8 record')
