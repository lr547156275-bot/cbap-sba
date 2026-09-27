# -*- coding: utf-8 -*-
# Option A: occupancy-bounded initial-release check + census fflush.
#
# Diagnosis (census-proven): availableCapacity is PAYLOAD-domain capacity
# (9,541,984,732 = 10e9*1000/1048 exactly) while oldApplied is WIRE-domain
# (fed from qp->m_rate).  When the link is saturated the check reduces to
# "oldApplied <= available", which fails by exactly the framing overhead
# (~464M) REGARDLESS of the new batch's size -- overlap admission was
# structurally impossible.
#
# Fix (minimal, state-free): bound = max(available, oldApplied).
#   - Under-loaded link (old <= available): bound == available, bit-identical
#     to the old check.  Every frozen scenario admits with old <= available
#     (S3/S5: 8G; S4: 9.5G < 9.542G), so all existing results are unchanged --
#     verified by byte regression.
#   - Saturated link: batchSum + oldRetained == oldApplied (algebraic identity
#     when residual==0 and the fill uses its budget), so the plan never
#     worsens observed occupancy and is admitted; migration then physically
#     retreats the old side.  The wire/payload mixing in grant budgets remains
#     and is documented as debt (Option B).
# Also: fflush after the census prints so an abort can never eat them again.
import io
import sys

SBA = '/work/simulation/src/point-to-point/model/cbap-sba.cc'
s = io.open(SBA, encoding='utf-8', errors='surrogateescape').read()

if 'occupancy bound' in s:
    print('already applied')
    sys.exit(0)

edits = []


def E(tag, old, new):
    edits.append((tag, old, new))


E('check-bound',
  '\t\t\t// Printed pass or fail so any abort self-explains from the log.\n'
  '\t\t\tstd::printf("SBA_LIFECYCLE_CHECK batch=%u link=%u batch_sum=%llu "\n'
  '\t\t\t\t"old_retained=%llu available=%llu margin=%lld\\n",\n'
  '\t\t\t\tbatchId, link->first, (unsigned long long)batchSum,\n'
  '\t\t\t\t(unsigned long long)oldRetained,\n'
  '\t\t\t\t(unsigned long long)link->second,\n'
  '\t\t\t\t(long long)((int64_t)link->second + (int64_t)ids.size() -\n'
  '\t\t\t\t\t(int64_t)batchSum - (int64_t)oldRetained));\n'
  '\t\t\tif (batchSum + oldRetained > link->second + ids.size())\n'
  '\t\t\t\tthrow std::logic_error(\n'
  '\t\t\t\t\t"SBA initial release violates planned capacity");',
  '\t\t\t// Occupancy bound.  availableCapacity is payload-domain while\n'
  '\t\t\t// oldApplied is wire-domain (census-proven: available ==\n'
  '\t\t\t// C*1000/1048 exactly); comparing the plan against available alone\n'
  '\t\t\t// therefore rejects EVERY admission on a saturated link by the\n'
  '\t\t\t// framing overhead, independent of batch size.  The invariant that\n'
  '\t\t\t// is actually safe and domain-consistent: the planned state must\n'
  '\t\t\t// never exceed max(available, observed occupancy) -- strict when\n'
  '\t\t\t// under-loaded (bit-identical to the old check there), and\n'
  '\t\t\t// plan-never-worsens when saturated (batchSum + oldRetained ==\n'
  '\t\t\t// oldApplied by construction when residual == 0).  The wire/payload\n'
  '\t\t\t// mixing inside grant budgets is documented debt, not hidden.\n'
  '\t\t\tconst uint64_t occupancyBound = link->second > oldApplied ?\n'
  '\t\t\t\tlink->second : oldApplied;\n'
  '\t\t\tstd::printf("SBA_LIFECYCLE_CHECK batch=%u link=%u batch_sum=%llu "\n'
  '\t\t\t\t"old_retained=%llu available=%llu bound=%llu margin=%lld\\n",\n'
  '\t\t\t\tbatchId, link->first, (unsigned long long)batchSum,\n'
  '\t\t\t\t(unsigned long long)oldRetained,\n'
  '\t\t\t\t(unsigned long long)link->second,\n'
  '\t\t\t\t(unsigned long long)occupancyBound,\n'
  '\t\t\t\t(long long)((int64_t)occupancyBound + (int64_t)ids.size() -\n'
  '\t\t\t\t\t(int64_t)batchSum - (int64_t)oldRetained));\n'
  '\t\t\tstd::fflush(stdout);\n'
  '\t\t\tif (batchSum + oldRetained > occupancyBound + ids.size())\n'
  '\t\t\t\tthrow std::logic_error(\n'
  '\t\t\t\t\t"SBA initial release violates planned capacity");')

E('census-flush',
  '\t\t\t\t(unsigned long long)(availableCapacity.count(l->first) ?\n'
  '\t\t\t\t\tavailableCapacity.find(l->first)->second : 0));\n'
  '\t}',
  '\t\t\t\t(unsigned long long)(availableCapacity.count(l->first) ?\n'
  '\t\t\t\t\tavailableCapacity.find(l->first)->second : 0));\n'
  '\t\tstd::fflush(stdout);\n'
  '\t}')

bad = 0
for tag, old, new in edits:
    n = s.count(old)
    print('%-14s count=%d %s' % (tag, n, 'OK' if n == 1 else 'FAIL'))
    if n != 1:
        bad += 1
if bad:
    print('ANCHOR FAIL -- nothing written')
    sys.exit(2)
for tag, old, new in edits:
    s = s.replace(old, new, 1)
io.open(SBA, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('occupancy-bound fix applied (cbap-sba.cc only)')
