# -*- coding: utf-8 -*-
# Item 1: make the migration actuation path observable in the unified
# rate_transition.csv, WITHOUT changing any control decision.
#
# Established by audit: EvaluateCbapSbaMigration() calls ChangeRate() directly
# and never goes through SetCbapRate(), so its 55 background-flow actuations per
# incast window (8 G -> 0.1 G -> 8 G) were invisible in rate_transition.csv.
# That is why I wrongly concluded CBAP does not migrate the background flow.
#
# Adds six columns and two new record sites.  Changes no condition, no rate, no
# threshold.  Schema extension of this AUDIT file is intentional; the regression
# check covers the RESULT files (flow_summary, port_summary,
# selected_link_timeseries, qlen, tx_serialization, pfc_events).
import io
import sys

HWH = '/work/simulation/src/point-to-point/model/rdma-hw.h'
HWC = '/work/simulation/src/point-to-point/model/rdma-hw.cc'
T = '/work/simulation/scratch/third.cc'


def need(s, pat, n, tag):
    if s.count(pat) != n:
        print('ANCHOR FAIL [%s]: expected %d found %d' % (tag, n, s.count(pat)))
        sys.exit(2)


h = io.open(HWH, encoding='utf-8', errors='surrogateescape').read()
c = io.open(HWC, encoding='utf-8', errors='surrogateescape').read()
t = io.open(T, encoding='utf-8', errors='surrogateescape').read()

if 'actuationKind' in h:
    print('already applied')
    sys.exit(0)

# ---- 1. extend the record ------------------------------------------------
a = '\t\tbool staleFeedback;\n\t\tbool capacityValid;\n\t};'
need(h, a, 1, 'h-record')
h = h.replace(a, '''		bool staleFeedback;
		bool capacityValid;
		// --- migration-path observability (item 1) ------------------------
		// role: 0 incast, 1 background (>= 1 GiB flow)
		// ownerBefore/After: 0 CBAP, 1 DCQCN (from qp->cbap.handedOff)
		// side: 0 new, 1 old, 2 not-in-migration
		// actuationKind: 0 setrate_dispatch, 1 setrate_noop,
		//                2 migration_dispatch, 3 migration_noop
		// appliedRateAfterBps: qp->m_rate AFTER the call, so one row shows
		//                      requested vs actually installed.
		uint32_t role;
		uint32_t ownerBefore;
		uint32_t ownerAfter;
		uint32_t side;
		uint32_t actuationKind;
		uint64_t appliedRateAfterBps;
	};''', 1)

a = '\tstatic void CbapGapSnapshot(uint64_t gapId, uint32_t boundary);'
need(h, a, 1, 'h-decl')
h = h.replace(a, a + '''
	// Item 1 observability helper.  Read-only with respect to the QP.
	static void TagCbapRateRecord(CbapRateRecord &rec, Ptr<RdmaQueuePair> qp,
		uint32_t kind, uint32_t ownerBefore);''', 1)

# ---- 2. helper definition ------------------------------------------------
a = 'void RdmaHw::SetCbapRate(CbapFlowRuntime &flow, uint64_t newRate,'
need(c, a, 1, 'c-setcbap')
c = c.replace(a, '''// Fill the observability fields of a rate record.  Reads only.
void RdmaHw::TagCbapRateRecord(CbapRateRecord &rec, Ptr<RdmaQueuePair> qp,
		uint32_t kind, uint32_t ownerBefore)
{
	rec.role = (qp->m_size >= (1ULL << 30)) ? 1u : 0u;
	rec.ownerBefore = ownerBefore;
	rec.ownerAfter = qp->cbap.handedOff ? 1u : 0u;
	rec.side = qp->cbap.migrationActive
		? (qp->cbap.migrationIsOldFlow ? 1u : 0u) : 2u;
	rec.actuationKind = kind;
	rec.appliedRateAfterBps = qp->m_rate.GetBitRate();
}

''' + a, 1)

# ---- 3. tag the SetCbapRate record ---------------------------------------
a = '''	qp->cbap.currentRateBps = newRate;
	qp->cbap.rootId = rootId;
	record.phaseAfter = qp->cbap.phase;
	s_cbapRateRecords.push_back(record);'''
need(c, a, 1, 'c-push')
c = c.replace(a, '''	qp->cbap.currentRateBps = newRate;
	qp->cbap.rootId = rootId;
	record.phaseAfter = qp->cbap.phase;
	// kind 0 = the rate actually changed, 1 = no-op (deadband / same value),
	// so replan volume can never be mistaken for command volume.
	TagCbapRateRecord(record, qp,
		(newRate != oldRate || pause != wasPaused) ? 0u : 1u,
		qp->cbap.handedOff ? 1u : 0u);
	s_cbapRateRecords.push_back(record);''', 1)

# ---- 4. record the migration actuation ----------------------------------
a = '''		if (currentRate != appliedRate) {
			flow->second.hw->ChangeRate(qp, DataRate(appliedRate));
			// rate_command_time: the instant the new pacing rate is installed.
			if (s_cbapActuationHook)
				s_cbapActuationHook(flow->first, currentRate, appliedRate);
		}'''
need(c, a, 1, 'c-mig')
c = c.replace(a, '''		{
			// Item 1: this path actuates through ChangeRate() and bypasses
			// SetCbapRate(), so without this record its dispatches are invisible
			// in rate_transition.csv.  Emitted for BOTH dispatch and no-op.
			const uint32_t ownerBefore = qp->cbap.handedOff ? 1u : 0u;
			CbapRateRecord mrec = {};
			mrec.timeNs = nowNs;
			mrec.epoch = s_cbapEpoch;
			mrec.batchId = qp->cbap.batchId;
			mrec.flowId = flow->first;
			mrec.phaseBefore = qp->cbap.phase;
			mrec.oldRateBps = currentRate;
			mrec.targetRateBps = qp->cbap.migrationTargetBps;
			mrec.newRateBps = appliedRate;
			mrec.reason = 7;                 // 7 = migration step
			mrec.rootId = qp->cbap.rootId;
			mrec.protectionFloorBps = qp->cbap.protectionFloorBps;
			mrec.capacityValid = true;
			if (currentRate != appliedRate) {
				flow->second.hw->ChangeRate(qp, DataRate(appliedRate));
				// rate_command_time: the instant the new pacing rate is installed.
				if (s_cbapActuationHook)
					s_cbapActuationHook(flow->first, currentRate, appliedRate);
				mrec.phaseAfter = qp->cbap.phase;
				TagCbapRateRecord(mrec, qp, 2u, ownerBefore);
			} else {
				mrec.phaseAfter = qp->cbap.phase;
				TagCbapRateRecord(mrec, qp, 3u, ownerBefore);
			}
			s_cbapRateRecords.push_back(mrec);
		}''', 1)

io.open(HWH, 'w', encoding='utf-8', errors='surrogateescape').write(h)
io.open(HWC, 'w', encoding='utf-8', errors='surrogateescape').write(c)

# ---- 5. extend the CSV writer -------------------------------------------
a = 'stale_feedback,capacity_valid\\n";'
need(t, a, 1, 't-hdr')
t = t.replace(a, 'stale_feedback,capacity_valid,"\n'
                 '\t\t\t"role,owner_before,owner_after,side,actuation_kind,"\n'
                 '\t\t\t"applied_rate_after_bps\\n";', 1)
a = "<< r.staleFeedback << ',' << r.capacityValid << '\\n';"
need(t, a, 1, 't-row')
t = t.replace(a, "<< r.staleFeedback << ',' << r.capacityValid\n"
                 "\t\t\t\t<< ',' << r.role << ',' << r.ownerBefore\n"
                 "\t\t\t\t<< ',' << r.ownerAfter << ',' << r.side\n"
                 "\t\t\t\t<< ',' << r.actuationKind\n"
                 "\t\t\t\t<< ',' << r.appliedRateAfterBps << '\\n';", 1)
io.open(T, 'w', encoding='utf-8', errors='surrogateescape').write(t)

print('migration audit wired')
print('  h: new record fields      : %d' % h.count('uint32_t actuationKind;'))
print('  h: helper declared        : %d' % h.count('static void TagCbapRateRecord'))
print('  c: helper defined         : %d' % c.count('void RdmaHw::TagCbapRateRecord'))
print('  c: SetCbapRate tagged     : %d' % c.count('TagCbapRateRecord(record, qp,'))
print('  c: migration dispatch tag : %d' % c.count('TagCbapRateRecord(mrec, qp, 2u'))
print('  c: migration noop tag     : %d' % c.count('TagCbapRateRecord(mrec, qp, 3u'))
print('  t: header cols added      : %d' % t.count('actuation_kind'))
print('  t: row fields added       : %d' % t.count('r.appliedRateAfterBps'))
