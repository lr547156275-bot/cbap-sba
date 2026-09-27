# -*- coding: utf-8 -*-
# Shakedown cells before the final matrix:
#   item 2: S1/S2/S6 x (D1, b040)  -- does the frozen candidate even run on
#           the scenarios it has never touched (small batches, dual
#           bottleneck)?  Any failure here is a finding, never retuned away.
#   item 3: DCTCP (CC_MODE 8) / TIMELY (CC_MODE 7) one S1 smoke each with the
#           unified flow_timing plumbing.
# D1/baseline cells derive from ckpt2_dcqcn_s*; b040 cells derive from
# scr8_b040.txt + the measured 8-11 key scenario delta.  FLOW_TIMING_FILE is
# appended where the source predates it (measurement plumbing, not behaviour).
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'

DELTA = {
    's1': {'FLOW_FILE': 's1_flow.txt', 'SIMULATOR_STOP_TIME': '2.1',
           'QLEN_MON_START': '1900000000', 'QLEN_MON_END': '2100000000',
           'ROUND_SCHEDULE_FILE': 's1_round_schedule.txt',
           'CBAP_LINK_FILE': 's1_cbap_link.txt',
           'CBAP_PATH_FILE': 's1_cbap_path.txt',
           'SCENARIO': 's1_fan16_256k_bg80',
           'FINAL_COLLECTIVE_FLOW_COUNT': '16'},
    's2': {'FLOW_FILE': 's2_flow.txt', 'SIMULATOR_STOP_TIME': '2.5',
           'QLEN_MON_END': '2500000000',
           'ROUND_SCHEDULE_FILE': 's2_round_schedule.txt',
           'CBAP_LINK_FILE': 's2_cbap_link.txt',
           'CBAP_PATH_FILE': 's2_cbap_path.txt',
           'SCENARIO': 's2_fan64_256k_bg80'},
    's6': {'FLOW_FILE': 's6_flow.txt', 'SIMULATOR_STOP_TIME': '2.5',
           'QLEN_MON_END': '2500000000',
           'ROUND_SCHEDULE_FILE': 's6_round_schedule.txt',
           'ROUND_TRACE_SELECTED_LINKS': '84:1,83:1',
           'CBAP_LINK_FILE': 's6_cbap_link.txt',
           'CBAP_PATH_FILE': 's6_cbap_path.txt',
           'SCENARIO': 's6_dual_bottleneck_256k_bg80',
           'FINAL_COLLECTIVE_FLOW_COUNT': '60',
           'APP_RATE_CAP_FLOW': '0,1'},
}

CELLS = []
for sc in ('s1', 's2', 's6'):
    CELLS.append(('sh_%s_d1' % sc, 'ckpt2_dcqcn_%s.txt' % sc, {}))
    CELLS.append(('sh_%s_b040' % sc, 'scr8_b040.txt', DELTA[sc]))
CELLS.append(('sm_s1_dctcp', 'ckpt2_dcqcn_s1.txt',
              {'CC_MODE': '8', 'ALGORITHM': 'dctcp'}))
CELLS.append(('sm_s1_timely', 'ckpt2_dcqcn_s1.txt',
              {'CC_MODE': '7', 'ALGORITHM': 'timely'}))


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(t):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', t, re.M)
    return m.group(1) if m else None


bad = 0
for tag, src, over in CELLS:
    sp = os.path.join(B, src)
    if not os.path.isfile(sp):
        print('MISSING %s' % sp)
        sys.exit(2)
    t = load(sp)
    old = outdir_of(t)
    new = '%s_out' % tag
    t = t.replace(old + '/', new + '/').replace(old, new)
    appended = []
    for k, v in over.items():
        pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
        if pat.search(t):
            t = pat.sub('%s %s' % (k, v), t)
        else:
            # scenario keys must exist in a CBAP source; refuse silent drift
            # there.  ALGORITHM/CC_MODE always exist.
            print('%s: key %s absent in %s -- refusing to append' %
                  (tag, k, src))
            sys.exit(2)
    if not re.search(r'^FLOW_TIMING_FILE\s', t, re.M):
        t = t.rstrip('\n') + '\nFLOW_TIMING_FILE %s/flow_timing.csv\n' % new
        appended.append('FLOW_TIMING_FILE')
    io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
            errors='surrogateescape').write(t)
    d = os.path.join(B, new)
    if not os.path.isdir(d):
        os.makedirs(d)
    print('wrote %-13s from %-22s (+%s)' %
          (tag, src, ','.join(appended) or 'nothing appended'))

# verify b040 cells differ from scr8_b040 only in the scenario keys + paths
print('')
for sc in ('s1', 's2', 's6'):
    tag = 'sh_%s_b040' % sc
    keys = set(DELTA[sc]) | {'FLOW_TIMING_FILE'}

    def norm(txt):
        out = []
        for ln in txt.split('\n'):
            w = ln.split()
            if not w or w[0] in keys:
                continue
            if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
                continue
            out.append(ln.strip())
        return out
    a = norm(load(os.path.join(B, 'scr8_b040.txt')))
    b2 = norm(load(os.path.join(B, '%s.txt' % tag)))
    extra = [x for x in a if x not in b2] + [x for x in b2 if x not in a]
    if extra:
        bad += 1
        print('%s DIFFERS beyond scenario keys: %s' % (tag, extra[:4]))
    else:
        print('%s clean (b040 frozen config + scenario keys only)' % tag)

hdr = '%-13s %-8s %-9s %-6s %-8s %-28s'
print('')
print(hdr % ('cell', 'CC_MODE', 'ALGO', 'STOP', 'QB2', 'SCENARIO'))
for tag, src, over in CELLS:
    t = load(os.path.join(B, '%s.txt' % tag))

    def g(k, d='-'):
        m = re.search(r'^%s\s+(\S+)' % k, t, re.M)
        return m.group(1) if m else d
    print(hdr % (tag, g('CC_MODE'), g('ALGORITHM'),
                 g('SIMULATOR_STOP_TIME'), g('CBAP_QUEUE_BAND_V2_ENABLE'),
                 g('SCENARIO')))
if bad:
    sys.exit(1)
print('')
print('8 shakedown cells OK')
