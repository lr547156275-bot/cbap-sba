# -*- coding: utf-8 -*-
# Item 1 (lifecycle accounting), stage 1: OBSERVABILITY + the explicit
# lifecycle guard.  No frozen parameter, checker, boundary or formula touched;
# the capacity check itself is unchanged (it now also PRINTS its inputs).
#
# Edits:
#  E1  old-side census in AdmitBatch explicitly excludes COLLECTING
#      (installed-but-unreleased holds no network rate; today its
#      appliedRateBps is 0 so this is belt-and-braces, per instruction).
#  E2  SBA_LIFECYCLE census: one line per admission with installed /
#      collecting / hold / startup / dcqcn_owned / finished counts and the
#      new-batch size.
#  E2b SBA_LIFECYCLE_CHECK: the exact arithmetic of the initial-release
#      conservation check (batch_sum, old_retained, available, margin) printed
#      for EVERY link, pass or fail -- so the next abort self-explains.
#  E3  SBA_PLAN_AT in PlanCbapSbaBatch: when each group is planned vs its
#      common release -- this pins down why batch B planned at t=2.000365 s
#      instead of its 2.0555 s release.
import io
import sys

SBA = '/work/simulation/src/point-to-point/model/cbap-sba.cc'
HWC = '/work/simulation/src/point-to-point/model/rdma-hw.cc'

s = io.open(SBA, encoding='utf-8', errors='surrogateescape').read()
c = io.open(HWC, encoding='utf-8', errors='surrogateescape').read()

if 'SBA_LIFECYCLE' in s:
    print('already applied')
    sys.exit(0)

edits = []


def E(tag, which, old, new):
    edits.append((tag, which, old, new))


E('E1-collecting-guard', 's',
  '\t\tif (existing->second.state == FINISHED ||\n'
  '\t\t\t\texisting->second.state == ADMISSION_HOLD)\n'
  '\t\t\tcontinue;',
  '\t\t// Lifecycle guard: an installed-but-unreleased flow (COLLECTING)\n'
  '\t\t// holds no network rate and must never enter the old-side census.\n'
  '\t\t// (Its appliedRateBps is 0 today; the guard makes the invariant\n'
  '\t\t// explicit instead of incidental.)\n'
  '\t\tif (existing->second.state == FINISHED ||\n'
  '\t\t\t\texisting->second.state == ADMISSION_HOLD ||\n'
  '\t\t\t\texisting->second.state == COLLECTING)\n'
  '\t\t\tcontinue;',)

E('E2-census', 's',
  '\tm_lastAdmitOldApplied = oldAppliedByLink;',
  '\tm_lastAdmitOldApplied = oldAppliedByLink;\n'
  '\t// SBA_LIFECYCLE: admission-time lifecycle census (observability only).\n'
  '\t{\n'
  '\t\tuint32_t nCol = 0, nHold = 0, nStart = 0, nOwn = 0, nFin = 0;\n'
  '\t\tfor (std::map<uint32_t, FlowState>::const_iterator it =\n'
  '\t\t\t\tm_flows.begin(); it != m_flows.end(); ++it) {\n'
  '\t\t\tswitch (it->second.state) {\n'
  '\t\t\tcase COLLECTING: nCol++; break;\n'
  '\t\t\tcase ADMISSION_HOLD: nHold++; break;\n'
  '\t\t\tcase STARTUP_SENDING: nStart++; break;\n'
  '\t\t\tcase DCQCN_OWNED: nOwn++; break;\n'
  '\t\t\tcase FINISHED: nFin++; break;\n'
  '\t\t\t}\n'
  '\t\t}\n'
  '\t\tstd::printf("SBA_LIFECYCLE batch=%u release_ns=%llu installed=%u "\n'
  '\t\t\t"collecting=%u hold=%u startup=%u dcqcn_owned=%u finished=%u "\n'
  '\t\t\t"new_batch=%u rho_init=%.4f\\n",\n'
  '\t\t\tbatchId, (unsigned long long)releaseTimeNs,\n'
  '\t\t\t(unsigned)m_flows.size(), nCol, nHold, nStart, nOwn, nFin,\n'
  '\t\t\t(unsigned)flows.size(), (double)m_initialReleaseRatio);\n'
  '\t\tfor (std::map<uint32_t, uint64_t>::const_iterator l =\n'
  '\t\t\t\toldAppliedByLink.begin(); l != oldAppliedByLink.end(); ++l)\n'
  '\t\t\tstd::printf("SBA_LIFECYCLE_LINK batch=%u link=%u old_applied=%llu "\n'
  '\t\t\t\t"available=%llu\\n", batchId, l->first,\n'
  '\t\t\t\t(unsigned long long)l->second,\n'
  '\t\t\t\t(unsigned long long)(availableCapacity.count(l->first) ?\n'
  '\t\t\t\t\tavailableCapacity.find(l->first)->second : 0));\n'
  '\t}',)

E('E2b-check-print', 's',
  '\t\t\tif (batchSum + oldRetained > link->second + ids.size())\n'
  '\t\t\t\tthrow std::logic_error(\n'
  '\t\t\t\t\t"SBA initial release violates planned capacity");',
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
  '\t\t\t\t\t"SBA initial release violates planned capacity");',)

E('E3-plan-at', 'c',
  '\tstd::vector<CbapSbaController::FlowInput> inputs;\n'
  '\tstd::map<uint32_t, Ptr<RdmaQueuePair> > qps;',
  '\t// SBA_PLAN_AT: when this group is planned vs when it releases.  This is\n'
  '\t// the line that determines whether a staggered group was planned early\n'
  '\t// against a stale old-side snapshot.\n'
  '\tstd::printf("SBA_PLAN_AT t=%llu group=%u application_ready=%llu "\n'
  '\t\t"common_release=%llu members=%u\\n",\n'
  '\t\t(unsigned long long)Simulator::Now().GetTimeStep(), groupId,\n'
  '\t\t(unsigned long long)group.applicationReadyNs,\n'
  '\t\t(unsigned long long)group.commonReleaseNs,\n'
  '\t\t(unsigned)group.members.size());\n'
  '\tstd::vector<CbapSbaController::FlowInput> inputs;\n'
  '\tstd::map<uint32_t, Ptr<RdmaQueuePair> > qps;',)

src = {'s': s, 'c': c}
bad = 0
for tag, which, old, new in edits:
    n = src[which].count(old)
    print('%-22s %s count=%d %s' % (tag, which, n, 'OK' if n == 1 else 'FAIL'))
    if n != 1:
        bad += 1
if bad:
    print('ANCHOR FAIL -- nothing written')
    sys.exit(2)
for tag, which, old, new in edits:
    src[which] = src[which].replace(old, new, 1)

# cbap-sba.cc needs <cstdio> for std::printf
if '#include <cstdio>' not in src['s']:
    i = src['s'].find('#include')
    src['s'] = src['s'][:i] + '#include <cstdio>\n' + src['s'][i:]
    print('added <cstdio> include to cbap-sba.cc')

io.open(SBA, 'w', encoding='utf-8', errors='surrogateescape').write(src['s'])
io.open(HWC, 'w', encoding='utf-8', errors='surrogateescape').write(src['c'])
print('census patch applied atomically (4 edits)')
