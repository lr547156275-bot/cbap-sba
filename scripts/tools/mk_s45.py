# -*- coding: utf-8 -*-
# Held-out validation cells: S4 and S5, three arms each (D1 / D3 / b040),
# generated from the EXACT scr8 configs with only the 8 scenario keys swapped.
# b040 is used unmodified (BMAX=0.04C, Qtarget=0.025*Q_abs) -- no retuning on
# S3 results, so S4/S5 remain a legitimate hold-out.
import io
import os
import re
import sys

B = '/work/simulation/experiment/scheme1_sba'

DELTA = {
    's4': {
        'FLOW_FILE': 's4_flow.txt',
        'SIMULATOR_STOP_TIME': '5.5',
        'QLEN_MON_END': '5500000000',
        'ROUND_SCHEDULE_FILE': 's4_round_schedule.txt',
        'CBAP_LINK_FILE': 's4_cbap_link.txt',
        'CBAP_PATH_FILE': 's4_cbap_path.txt',
        'SCENARIO': 's4_fan64_1m_bg95',
        'APP_RATE_CAP_BPS': '9500000000',
    },
    's5': {
        'FLOW_FILE': 's5_flow.txt',
        'SIMULATOR_STOP_TIME': '6.0',
        'QLEN_MON_END': '6000000000',
        'ROUND_SCHEDULE_FILE': 's5_round_schedule.txt',
        'CBAP_LINK_FILE': 's5_cbap_link.txt',
        'CBAP_PATH_FILE': 's5_cbap_path.txt',
        'SCENARIO': 's5_fan64_4m_bg80',
        'APP_RATE_CAP_BPS': '8000000000',
    },
}
ARMS = [('d1', 'scr8_d1.txt'), ('d3', 'scr8_d3.txt'), ('b040', 'scr8_b040.txt')]


def load(p):
    return io.open(p, encoding='utf-8', errors='surrogateescape').read()


def outdir_of(txt):
    m = re.search(r'^FLOW_SUMMARY_FILE\s+(\S+)/', txt, re.M)
    return m.group(1) if m else None


# scenario data files must exist before any cell is written
for sc, delta in DELTA.items():
    for k in ('FLOW_FILE', 'ROUND_SCHEDULE_FILE', 'CBAP_LINK_FILE',
              'CBAP_PATH_FILE'):
        p = os.path.join(B, delta[k])
        if not os.path.isfile(p):
            print('MISSING scenario file %s' % p)
            sys.exit(2)

made = []
for sc in ('s4', 's5'):
    for arm, src in ARMS:
        tag = '%sv_%s' % (sc, arm)
        txt = load(os.path.join(B, src))
        old = outdir_of(txt)
        if not old:
            print('%s: no outdir in %s' % (tag, src))
            sys.exit(2)
        new = '%s_out' % tag
        txt = txt.replace(old + '/', new + '/').replace(old, new)
        # every delta key must already EXIST in the source (replace, never
        # append) -- an appended key would mean the source config drifted.
        for k, v in DELTA[sc].items():
            pat = re.compile(r'^%s\s+.*$' % re.escape(k), re.M)
            if not pat.search(txt):
                print('%s: key %s absent in %s -- refusing to append' %
                      (tag, k, src))
                sys.exit(2)
            txt = pat.sub('%s %s' % (k, v), txt)
        io.open(os.path.join(B, '%s.txt' % tag), 'w', encoding='utf-8',
                errors='surrogateescape').write(txt)
        d = os.path.join(B, new)
        if not os.path.isdir(d):
            os.makedirs(d)
        made.append(tag)
        print('wrote %-10s.txt -> %s/  (from %s)' % (tag, new, src))

# ---- assert: each cell differs from its scr8 source ONLY in the 8 keys ----
KEYS = set()
for d in DELTA.values():
    KEYS.update(d)
print('')
print('=== diff check vs scr8 sources (paths + 8 scenario keys excluded) ===')


def norm(txt):
    out = []
    for ln in txt.split('\n'):
        w = ln.split()
        if not w or w[0] in KEYS:
            continue
        if len(w) >= 2 and ('_out/' in w[1] or w[1].endswith('_out')):
            continue
        out.append(ln.strip())
    return out


bad = 0
for sc in ('s4', 's5'):
    for arm, src in ARMS:
        tag = '%sv_%s' % (sc, arm)
        a = norm(load(os.path.join(B, src)))
        b = norm(load(os.path.join(B, '%s.txt' % tag)))
        extra = [x for x in a if x not in b] + [x for x in b if x not in a]
        if extra:
            bad += 1
            print('  %s DIFFERS: %s' % (tag, extra[:5]))
        else:
            print('  %-10s clean (only scenario keys + paths)' % tag)

print('')
hdr = '%-10s %-8s %-6s %-22s %-6s %-8s %-8s'
print(hdr % ('cell', 'CC_MODE', 'STOP', 'SCENARIO', 'MIG', 'QB2', 'BMAX'))
for tag in made:
    txt = load(os.path.join(B, '%s.txt' % tag))

    def g(k, d='-'):
        m = re.search(r'^%s\s+(\S+)' % k, txt, re.M)
        return m.group(1) if m else d
    print(hdr % (tag, g('CC_MODE'), g('SIMULATOR_STOP_TIME'), g('SCENARIO'),
                 g('CBAP_MIGRATION_ENABLE'), g('CBAP_QUEUE_BAND_V2_ENABLE'),
                 g('CBAP_QB2_BMAX_RATIO')))
if bad:
    print('CELL CONSTRUCTION FAIL')
    sys.exit(1)
print('')
print('6 held-out cells OK')
