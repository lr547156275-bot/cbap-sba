# -*- coding: utf-8 -*-
# D4v2: predictive headroom top-up behind CBAP_QUEUE_BAND_V2_ENABLE (default 0).
#
# Design mapping onto the existing, unit-tested controller:
#   - The zone machine in QueueControllerEpoch already IS the required
#     four-band-with-hysteresis machine (GREEN/HOLD/DRAIN/RED; RED enters at
#     qSafe >= qAbs i.e. qStop >= qRed, exits only at qStop <= qHigh; !pfcSafe
#     forces RED; exitRecoveryPending forbids jumping back to GREEN).  v2 does
#     NOT modify it -- it only replaces the `desired` law when the flag is on.
#   - Q_pred := qStop (the existing prediction with the pending-command arrival
#     envelope over H_guard).  packet margin := mSafe.  H_eff := qcHGuardS.
#   - law: boost = min(BMAX, max(0, Q_target - Q_pred) * 8 / H_eff), GREEN only.
#     HOLD holds/decays, DRAIN drains gently (<= min(2*BMAX, drainMax)), RED is
#     the existing forced drain.  Veto when Q_pred would cross Q_red.
#   - Lease: boost expires H_eff after it became effective unless refreshed.
#   - Consumption: added to capWire in the static-cap block (the ONLY path that
#     reaches the target under steadyCapEnable -- effectivePlannerBudgetBps is
#     bypassed there, proven in the v1 round).  min(demand, cap) preserved;
#     incastWire = totalTarget - bgWire, so the background flow can never
#     receive boost; admission base, migration targets and floors untouched.
#   - No global sumR <= C clamp is added anywhere.
#
# Every anchor is verified across all three files BEFORE any file is written.
import io
import sys

HWH = '/work/simulation/src/point-to-point/model/rdma-hw.h'
HWC = '/work/simulation/src/point-to-point/model/rdma-hw.cc'
T = '/work/simulation/scratch/third.cc'

h = io.open(HWH, encoding='utf-8', errors='surrogateescape').read()
c = io.open(HWC, encoding='utf-8', errors='surrogateescape').read()
t = io.open(T, encoding='utf-8', errors='surrogateescape').read()

if 'queueBandV2Enable' in h:
    print('already applied')
    sys.exit(0)

edits = []


def E(tag, which, old, new):
    edits.append((tag, which, old, new))


# ===================== rdma-hw.h ==========================================
E('h1-config-fields', 'h',
  '\t\tbool queueBandEnable;',
  '\t\tbool queueBandEnable;\n'
  '\t\t// D4v2 (CBAP_QUEUE_BAND_V2_ENABLE): predictive headroom top-up.\n'
  '\t\t// Independent of queueBandEnable (v1, INVALID_OVERBOOST_POLICY) and\n'
  '\t\t// mutually exclusive with it at config parse.  Default false: D1/D2/D3\n'
  '\t\t// and every flag=0 run are byte-identical.\n'
  '\t\tbool queueBandV2Enable;\n'
  '\t\tdouble qb2BmaxRatio;      // BMAX = ratio * C_wire; parse rejects > 0.10\n'
  '\t\tdouble qb2QTargetRatio;   // Q_target = ratio * Q_abs')

E('h2-config-ctor', 'h',
  '\t\t\t  queueBandEnable(false),',
  '\t\t\t  queueBandEnable(false),\n'
  '\t\t\t  queueBandV2Enable(false), qb2BmaxRatio(0.0),\n'
  '\t\t\t  qb2QTargetRatio(0.0),')

E('h3-runtime-fields', 'h',
  '\t\tuint64_t qcDrainTargetBps;\n'
  '\t\tuint64_t qcGenerationCounter;',
  '\t\tuint64_t qcDrainTargetBps;\n'
  '\t\t// --- D4v2 state (audit + lease; zero and inert when flag off) ------\n'
  '\t\t// veto codes: 0 none, 1 boost vetoed (Q_pred past Q_red), 2 boost\n'
  '\t\t// clamped to Q_red headroom, 3 lease expired, 5 RED zone forced.\n'
  '\t\tuint64_t qb2LeaseExpireNs;\n'
  '\t\tuint32_t qb2VetoReason;\n'
  '\t\tuint64_t qb2RequestedBps;      // law value before veto/clamp\n'
  '\t\tuint64_t qb2AppliedBoostBps;   // boost the capWire actually consumed\n'
  '\t\tuint64_t qb2QLowBytes;         // derived band bounds, exported for\n'
  '\t\tuint64_t qb2QHighBytes;        // the trace manifest\n'
  '\t\tuint64_t qb2QRedBytes;\n'
  '\t\tuint64_t qb2QAbsBytes;\n'
  '\t\tuint64_t qcGenerationCounter;')

E('h4-runtime-ctor', 'h',
  '\t\t\t  qcPendingGeneration(0), qcDrainTargetBps(0),',
  '\t\t\t  qcPendingGeneration(0), qcDrainTargetBps(0),\n'
  '\t\t\t  qb2LeaseExpireNs(0), qb2VetoReason(0), qb2RequestedBps(0),\n'
  '\t\t\t  qb2AppliedBoostBps(0), qb2QLowBytes(0), qb2QHighBytes(0),\n'
  '\t\t\t  qb2QRedBytes(0), qb2QAbsBytes(0),')

E('h5-snapshot', 'h',
  '\t\tbool handoffPending;\n'
  '\t};',
  '\t\tbool handoffPending;\n'
  '\t\t// D4v2 observability (all zero when the v2 flag is off)\n'
  '\t\tuint64_t qb2LeaseExpireNs, qb2RequestedBps, qb2AppliedBoostBps;\n'
  '\t\tuint32_t qb2VetoReason;\n'
  '\t\tuint64_t qb2QLowBytes, qb2QHighBytes, qb2QRedBytes, qb2QAbsBytes;\n'
  '\t\tuint64_t steadyIncastTargetWire, steadyBackgroundWire;\n'
  '\t\tuint64_t steadyInputBudgetBps, steadyReturnedTargetSumBps;\n'
  '\t};')

# ===================== rdma-hw.cc =========================================
E('c0-bounds-export', 'c',
  '\tif (!(qLow > 0.0L && qLow < qHigh && qHigh < qRed && qRed < qAbs)) {\n'
  '\t\truntime.qcBandInvalid = 1;\n'
  '\t\treturn;\n'
  '\t}',
  '\tif (!(qLow > 0.0L && qLow < qHigh && qHigh < qRed && qRed < qAbs)) {\n'
  '\t\truntime.qcBandInvalid = 1;\n'
  '\t\treturn;\n'
  '\t}\n'
  '\t// Derived band bounds exported for the v2 trace manifest.  Audit-only\n'
  '\t// fields: nothing reads them for control.\n'
  '\truntime.qb2QLowBytes = (uint64_t)qLow;\n'
  '\truntime.qb2QHighBytes = (uint64_t)qHigh;\n'
  '\truntime.qb2QRedBytes = (uint64_t)qRed;\n'
  '\truntime.qb2QAbsBytes = (uint64_t)qAbs;')

E('c1-audit-copy', 'c',
  '\tout->inRed = it->second.qcInRed;\n'
  '\treturn true;',
  '\tout->inRed = it->second.qcInRed;\n'
  '\tout->qb2LeaseExpireNs = it->second.qb2LeaseExpireNs;\n'
  '\tout->qb2RequestedBps = it->second.qb2RequestedBps;\n'
  '\tout->qb2AppliedBoostBps = it->second.qb2AppliedBoostBps;\n'
  '\tout->qb2VetoReason = it->second.qb2VetoReason;\n'
  '\tout->qb2QLowBytes = it->second.qb2QLowBytes;\n'
  '\tout->qb2QHighBytes = it->second.qb2QHighBytes;\n'
  '\tout->qb2QRedBytes = it->second.qb2QRedBytes;\n'
  '\tout->qb2QAbsBytes = it->second.qb2QAbsBytes;\n'
  '\tout->steadyIncastTargetWire = it->second.lastSteadyIncastTargetWire;\n'
  '\tout->steadyBackgroundWire = it->second.lastMeasuredBackgroundWire;\n'
  '\tout->steadyInputBudgetBps = it->second.lastInputBudgetBps;\n'
  '\tout->steadyReturnedTargetSumBps = it->second.lastReturnedTargetSumBps;\n'
  '\treturn true;')

E('c2-forcing-cond', 'c',
  '\t\tif (s_cbapConfig.steadyCapEnable && !s_cbapConfig.queueBandEnable){\n'
  '\t\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\t}',
  '\t\tif (s_cbapConfig.steadyCapEnable && !s_cbapConfig.queueBandEnable &&\n'
  '\t\t\t\t!s_cbapConfig.queueBandV2Enable){\n'
  '\t\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\t}')

E('c3-red-veto-mark', 'c',
  '\tif (zone == 3) {\n'
  '\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\truntime.qcDrainCommandedBps = (uint64_t)drainMax;\n'
  '\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\truntime.qcDrainTargetBps = (uint64_t)drainMax;\n'
  '\t\truntime.qcPendingGeneration = 0;\n'
  '\t\truntime.qcPendingEtaNs = 0;\n'
  '\t\treturn;\n'
  '\t}',
  '\tif (zone == 3) {\n'
  '\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\truntime.qcDrainCommandedBps = (uint64_t)drainMax;\n'
  '\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\truntime.qcDrainTargetBps = (uint64_t)drainMax;\n'
  '\t\truntime.qcPendingGeneration = 0;\n'
  '\t\truntime.qcPendingEtaNs = 0;\n'
  '\t\tif (s_cbapConfig.queueBandV2Enable){\n'
  '\t\t\truntime.qb2VetoReason = 5;      // RED: forced veto + full drain\n'
  '\t\t\truntime.qb2RequestedBps = 0;\n'
  '\t\t\truntime.qb2AppliedBoostBps = 0;\n'
  '\t\t}\n'
  '\t\treturn;\n'
  '\t}',)

E('c4-lease-set', 'c',
  '\t\truntime.qcActualEffectTimeNs = nowNs;\n'
  '\t\truntime.qcBoostCommandedBps = 0;',
  '\t\t// D4v2 lease: the boost that just became effective may persist for at\n'
  '\t\t// most H_eff without a refresh.  The controller normally refreshes\n'
  '\t\t// every epoch (5 us << H_eff); the lease only bites if it stalls.\n'
  '\t\tif (s_cbapConfig.queueBandV2Enable)\n'
  '\t\t\truntime.qb2LeaseExpireNs = nowNs + (uint64_t)(hGuard * 1e9L);\n'
  '\t\truntime.qcActualEffectTimeNs = nowNs;\n'
  '\t\truntime.qcBoostCommandedBps = 0;')

E('c5-v2-law', 'c',
  '\t\t\tdesired = -drainMax * pressure;\n'
  '\t\t}\n'
  '\t}\n'
  '\tif (runtime.qcExitRecoveryPending && desired > 0.0L)',
  '\t\t\tdesired = -drainMax * pressure;\n'
  '\t\t}\n'
  '\t}\n'
  '\t// ---- D4v2: predictive headroom top-up --------------------------------\n'
  '\t// Replaces only the LAW; zones, hysteresis, RED, exit-recovery, handoff\n'
  '\t// and floor clamps below all still apply to the v2 value.\n'
  '\t//   boost = min(BMAX, max(0, Q_target - Q_pred) * 8 / H_eff)\n'
  '\t// with Q_pred = qStop (prediction incl. the pending arrival envelope).\n'
  '\tif (s_cbapConfig.queueBandV2Enable) {\n'
  '\t\tconst long double bMax =\n'
  '\t\t\t(long double)s_cbapConfig.qb2BmaxRatio * cWire;\n'
  '\t\tconst long double qTgt =\n'
  '\t\t\t(long double)s_cbapConfig.qb2QTargetRatio * qAbs;\n'
  '\t\tlong double v2 = 0.0L;\n'
  '\t\tuint32_t veto = 0;\n'
  '\t\tlong double cur = (long double)runtime.qcBoostEffectiveBps;\n'
  '\t\tif (cur > 0.0L && nowNs > runtime.qb2LeaseExpireNs) {\n'
  '\t\t\t// lease expired without refresh: the boost may not persist\n'
  '\t\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\t\tcur = 0.0L;\n'
  '\t\t\tveto = 3;\n'
  '\t\t}\n'
  '\t\tif (zone == 0) {\n'
  '\t\t\t// GREEN: top up only the predicted gap below Q_target.\n'
  '\t\t\tconst long double head = qTgt - qStop;\n'
  '\t\t\tv2 = head > 0.0L ? head * 8.0L / hGuard : 0.0L;\n'
  '\t\t\truntime.qb2RequestedBps = (uint64_t)(v2 > 0.0L ? v2 : 0.0L);\n'
  '\t\t\tif (v2 > bMax)\n'
  '\t\t\t\tv2 = bMax;\n'
  '\t\t\t// veto: never let the boosted prediction cross Q_red (M_safe and\n'
  '\t\t\t// the PFC guard then keep Q_abs out of reach; !pfcSafe is already\n'
  '\t\t\t// a RED condition).\n'
  '\t\t\tconst long double roomRed = (qRed - qStop) * 8.0L / hGuard;\n'
  '\t\t\tif (roomRed <= 0.0L) {\n'
  '\t\t\t\tv2 = 0.0L;\n'
  '\t\t\t\tveto = 1;\n'
  '\t\t\t} else if (v2 > roomRed) {\n'
  '\t\t\t\tv2 = roomRed;\n'
  '\t\t\t\tveto = 2;\n'
  '\t\t\t}\n'
  '\t\t} else if (zone == 1) {\n'
  '\t\t\t// HOLD: keep the current boost, slow decay (~0.99 per 5 us epoch;\n'
  '\t\t\t// sub-deadband steps are held by the command deadband, which is\n'
  '\t\t\t// the specified hold-or-slowly-decay behaviour).\n'
  '\t\t\truntime.qb2RequestedBps = (uint64_t)cur;\n'
  '\t\t\tv2 = cur * 0.99L;\n'
  '\t\t\tif (v2 > bMax)\n'
  '\t\t\t\tv2 = bMax;\n'
  '\t\t} else {\n'
  '\t\t\t// DRAIN: boost = 0, gentle drain proportional to pressure and\n'
  '\t\t\t// scaled to the boost budget (excess of this magnitude is what a\n'
  '\t\t\t// small top-up can have caused), never above drainMax.\n'
  '\t\t\truntime.qb2RequestedBps = 0;\n'
  '\t\t\tconst long double span = qRed - qHigh;\n'
  '\t\t\tlong double pressure = span > 0.0L ?\n'
  '\t\t\t\t(qStop - qHigh) / span : 1.0L;\n'
  '\t\t\tif (pressure < 0.0L)\n'
  '\t\t\t\tpressure = 0.0L;\n'
  '\t\t\tif (pressure > 1.0L)\n'
  '\t\t\t\tpressure = 1.0L;\n'
  '\t\t\tlong double d2 = 2.0L * bMax;\n'
  '\t\t\tif (d2 > drainMax)\n'
  '\t\t\t\td2 = drainMax;\n'
  '\t\t\tv2 = -d2 * pressure;\n'
  '\t\t}\n'
  '\t\tdesired = v2;\n'
  '\t\truntime.qb2VetoReason = veto;\n'
  '\t}\n'
  '\tif (runtime.qcExitRecoveryPending && desired > 0.0L)')

E('c6-capwire-consume', 'c',
  '\t\t\t\tif (s_cbapConfig.queueBandEnable){\n'
  '\t\t\t\t\tconst long double dWire =\n'
  '\t\t\t\t\t\t(long double)lit->second.qcBoostEffectiveBps\n'
  '\t\t\t\t\t\t- (long double)lit->second.qcDrainTargetBps;\n'
  '\t\t\t\t\tcapWire += dWire;\n'
  '\t\t\t\t\tif (capWire < 0.0L)\n'
  '\t\t\t\t\t\tcapWire = 0.0L;\n'
  '\t\t\t\t}',
  '\t\t\t\tif (s_cbapConfig.queueBandEnable){\n'
  '\t\t\t\t\tconst long double dWire =\n'
  '\t\t\t\t\t\t(long double)lit->second.qcBoostEffectiveBps\n'
  '\t\t\t\t\t\t- (long double)lit->second.qcDrainTargetBps;\n'
  '\t\t\t\t\tcapWire += dWire;\n'
  '\t\t\t\t\tif (capWire < 0.0L)\n'
  '\t\t\t\t\t\tcapWire = 0.0L;\n'
  '\t\t\t\t}\n'
  '\t\t\t\telse if (s_cbapConfig.queueBandV2Enable){\n'
  '\t\t\t\t\t// D4v2: leased, ephemeral top-up.  Never enters\n'
  '\t\t\t\t\t// admissionBaseCapacityBps, migration targets or background\n'
  '\t\t\t\t\t// floors; min(demand, cap) below still bounds the target and\n'
  '\t\t\t\t\t// incastWire = totalTarget - bgWire keeps the background flow\n'
  '\t\t\t\t\t// unboosted.  Wire domain on both sides.\n'
  '\t\t\t\t\tconst uint64_t v2now =\n'
  '\t\t\t\t\t\t(uint64_t)Simulator::Now().GetTimeStep();\n'
  '\t\t\t\t\tlong double b =\n'
  '\t\t\t\t\t\t(long double)lit->second.qcBoostEffectiveBps;\n'
  '\t\t\t\t\tif (v2now > lit->second.qb2LeaseExpireNs)\n'
  '\t\t\t\t\t\tb = 0.0L;               // lease expired: no carry-over\n'
  '\t\t\t\t\tconst long double dr =\n'
  '\t\t\t\t\t\t(long double)lit->second.qcDrainTargetBps;\n'
  '\t\t\t\t\tlit->second.qb2AppliedBoostBps = (uint64_t)b;\n'
  '\t\t\t\t\tcapWire += b - dr;\n'
  '\t\t\t\t\tif (capWire < 0.0L)\n'
  '\t\t\t\t\t\tcapWire = 0.0L;\n'
  '\t\t\t\t}')

E('c7-inactive-zero', 'c',
  '\t\truntime.qcZone = 0;\n'
  '\t\truntime.qcQStopBytes = queueBytes;\n'
  '\t\truntime.qcQSafeBytes = (uint64_t)(q0 + mSafe);\n'
  '\t\treturn;\n'
  '\t}',
  '\t\truntime.qcZone = 0;\n'
  '\t\truntime.qcQStopBytes = queueBytes;\n'
  '\t\truntime.qcQSafeBytes = (uint64_t)(q0 + mSafe);\n'
  '\t\t// D4v2: no owned rates means no active batch -> boost audit zeroed so\n'
  '\t\t// the trace cannot show a stale boost between batches.\n'
  '\t\truntime.qb2RequestedBps = 0;\n'
  '\t\truntime.qb2AppliedBoostBps = 0;\n'
  '\t\truntime.qb2VetoReason = 0;\n'
  '\t\treturn;\n'
  '\t}')

# ===================== third.cc ===========================================
E('t1-globals', 't',
  'string cbap_qc_trace_file;\n'
  'static FILE *cbap_qc_trace_csv = NULL;',
  'string cbap_qc_trace_file;\n'
  'static FILE *cbap_qc_trace_csv = NULL;\n'
  '// D4v2 controller trace + config (CBAP_QB2_*).  *_set flags enforce\n'
  '// fail-fast: enabling v2 without explicit values is a config error, never\n'
  '// a silent default.\n'
  'string cbap_qb2_trace_file;\n'
  'static FILE *cbap_qb2_trace_csv = NULL;\n'
  'static std::set<uint32_t> cbap_qb2_manifest_links;\n'
  'uint32_t cbap_qb2_enable = 0;\n'
  'double cbap_qb2_bmax_ratio = 0.0, cbap_qb2_qtarget_ratio = 0.0;\n'
  'uint32_t cbap_qb2_bmax_set = 0, cbap_qb2_qtarget_set = 0;')

E('t2-sampler', 't',
  '// Queue-controller trace.  Records every field item 9 requires so the two\n'
  '// preflight runs can be audited without re-deriving anything.\n'
  'static void SampleCbapQcTrace(uint32_t linkId, uint64_t queueBytes,\n'
  '\t\tuint64_t capacityBps){',
  '// D4v2 controller trace: one row per control epoch per traced link, plus a\n'
  '// #MANIFEST comment line per link on the first valid sample so every run is\n'
  '// self-describing.  Column derivations:\n'
  '//   queue_predicted_bytes = Q_stop (prediction incl. pending envelope)\n'
  '//   pending_excess_bytes  = Q_stop - Q_current (predicted accumulation)\n'
  '//   service_wire_bps      = link line rate (work-conserving egress)\n'
  '//   aggregate_requested   = static cap fed to the fill (base + boost)\n'
  '//   aggregate_applied     = incast targets + measured background wire\n'
  '//   veto_reason: 0 none, 1 boost vetoed (Q_pred past Q_red), 2 clamped to\n'
  '//   Q_red headroom, 3 lease expired, 5 RED zone forced.\n'
  'static void SampleCbapQb2Trace(uint32_t linkId, uint64_t queueBytes,\n'
  '\t\tuint64_t capacityBps){\n'
  '\tif (!cbap_qb2_trace_csv)\n'
  '\t\treturn;\n'
  '\tRdmaHw::CbapQcSnapshot qc;\n'
  '\tif (!RdmaHw::GetCbapQcStateForAudit(linkId, &qc))\n'
  '\t\treturn;\n'
  '\tif (qc.qb2QAbsBytes > 0 &&\n'
  '\t\t\tcbap_qb2_manifest_links.insert(linkId).second){\n'
  '\t\tfprintf(cbap_qb2_trace_csv,\n'
  '\t\t\t"#MANIFEST,link_id=%u,steady_cap_fraction=%.6f,rho=%.6f,"\n'
  '\t\t\t"bmax_ratio=%.6f,bmax_wire_bps=%.0f,qtarget_ratio=%.6f,"\n'
  '\t\t\t"qtarget_bytes=%.0f,q_low=%lu,q_high=%lu,q_red=%lu,q_abs=%lu,"\n'
  '\t\t\t"h_eff_us=%.3f,queue_band_v2=%u,queue_band_v1=%u,migration=%u,"\n'
  '\t\t\t"steady_cap=%u,seed=%u\\n",\n'
  '\t\t\tlinkId, cbap_steady_cap_fraction, cbap_rho,\n'
  '\t\t\tcbap_qb2_bmax_ratio,\n'
  '\t\t\tcbap_qb2_bmax_ratio * (double)capacityBps,\n'
  '\t\t\tcbap_qb2_qtarget_ratio,\n'
  '\t\t\tcbap_qb2_qtarget_ratio * (double)qc.qb2QAbsBytes,\n'
  '\t\t\t(unsigned long)qc.qb2QLowBytes,\n'
  '\t\t\t(unsigned long)qc.qb2QHighBytes,\n'
  '\t\t\t(unsigned long)qc.qb2QRedBytes,\n'
  '\t\t\t(unsigned long)qc.qb2QAbsBytes,\n'
  '\t\t\tcbap_qc_h_guard_us, cbap_qb2_enable, cbap_queue_band,\n'
  '\t\t\tcbap_migration_enable ? 1u : 0u, cbap_steady_cap, sim_seed);\n'
  '\t\tprintf("QB2_MANIFEST link=%u bmax_ratio=%.4f qtarget_ratio=%.4f "\n'
  '\t\t\t"q_abs=%lu h_eff_us=%.3f\\n", linkId, cbap_qb2_bmax_ratio,\n'
  '\t\t\tcbap_qb2_qtarget_ratio, (unsigned long)qc.qb2QAbsBytes,\n'
  '\t\t\tcbap_qc_h_guard_us);\n'
  '\t}\n'
  '\tconst char *zone = qc.zone == 3 ? "RED" : (qc.zone == 2 ? "DRAIN" :\n'
  '\t\t(qc.zone == 1 ? "HOLD" : "GREEN"));\n'
  '\tconst uint64_t pendingExcess = qc.qStopBytes > qc.q0Bytes ?\n'
  '\t\tqc.qStopBytes - qc.q0Bytes : 0;\n'
  '\tfprintf(cbap_qb2_trace_csv,\n'
  '\t\t"%lu,%u,%u,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%s,%u,"\n'
  '\t\t"%lu,%lu\\n",\n'
  '\t\t(unsigned long)Simulator::Now().GetTimeStep(),\n'
  '\t\tqc.activeGenerationId,\n'
  '\t\tqc.ownsRates ? 1u : 0u,\n'
  '\t\t(unsigned long)qc.q0Bytes,\n'
  '\t\t(unsigned long)qc.qStopBytes,\n'
  '\t\t(unsigned long)pendingExcess,\n'
  '\t\t(unsigned long)qc.arrivalSafeWireBps,\n'
  '\t\t(unsigned long)capacityBps,\n'
  '\t\t(unsigned long)qc.steadyIncastTargetWire,\n'
  '\t\t(unsigned long)qc.qb2RequestedBps,\n'
  '\t\t(unsigned long)qc.qb2AppliedBoostBps,\n'
  '\t\t(unsigned long)qc.qb2LeaseExpireNs,\n'
  '\t\t(unsigned long)qc.drainTargetBps,\n'
  '\t\t(unsigned long)qc.steadyInputBudgetBps,\n'
  '\t\t(unsigned long)(qc.steadyReturnedTargetSumBps +\n'
  '\t\t\tqc.steadyBackgroundWire),\n'
  '\t\tzone, qc.qb2VetoReason,\n'
  '\t\t(unsigned long)qc.steadyBackgroundWire,\n'
  '\t\t(unsigned long)qc.steadyReturnedTargetSumBps);\n'
  '}\n'
  '\n'
  '// Queue-controller trace.  Records every field item 9 requires so the two\n'
  '// preflight runs can be audited without re-deriving anything.\n'
  'static void SampleCbapQcTrace(uint32_t linkId, uint64_t queueBytes,\n'
  '\t\tuint64_t capacityBps){')

E('t3-callsite', 't',
  '\tSampleCbapQcTrace(linkId, snapshot.queueBytes, snapshot.capacityBps);',
  '\tSampleCbapQcTrace(linkId, snapshot.queueBytes, snapshot.capacityBps);\n'
  '\tSampleCbapQb2Trace(linkId, snapshot.queueBytes, snapshot.capacityBps);')

E('t4-parse', 't',
  '\t\t\telse if(key.compare("CBAP_QC_TRACE_FILE")==0)\n'
  '\t\t\t\tconf>>cbap_qc_trace_file;',
  '\t\t\telse if(key.compare("CBAP_QC_TRACE_FILE")==0)\n'
  '\t\t\t\tconf>>cbap_qc_trace_file;\n'
  '\t\t\telse if(key.compare("CBAP_QUEUE_BAND_V2_ENABLE")==0){\n'
  '\t\t\t\tconf>>cbap_qb2_enable;\n'
  '\t\t\t\tstd::cout << "CBAP_QUEUE_BAND_V2_ENABLE\\t\\t"\n'
  '\t\t\t\t\t<< cbap_qb2_enable << "\\n";\n'
  '\t\t\t}\n'
  '\t\t\telse if(key.compare("CBAP_QB2_BMAX_RATIO")==0){\n'
  '\t\t\t\tconf>>cbap_qb2_bmax_ratio;\n'
  '\t\t\t\tcbap_qb2_bmax_set = 1;\n'
  '\t\t\t\tstd::cout << "CBAP_QB2_BMAX_RATIO\\t\\t"\n'
  '\t\t\t\t\t<< cbap_qb2_bmax_ratio << "\\n";\n'
  '\t\t\t}\n'
  '\t\t\telse if(key.compare("CBAP_QB2_QTARGET_RATIO")==0){\n'
  '\t\t\t\tconf>>cbap_qb2_qtarget_ratio;\n'
  '\t\t\t\tcbap_qb2_qtarget_set = 1;\n'
  '\t\t\t\tstd::cout << "CBAP_QB2_QTARGET_RATIO\\t\\t"\n'
  '\t\t\t\t\t<< cbap_qb2_qtarget_ratio << "\\n";\n'
  '\t\t\t}\n'
  '\t\t\telse if(key.compare("CBAP_QB2_TRACE_FILE")==0)\n'
  '\t\t\t\tconf>>cbap_qb2_trace_file;')

E('t5-assign-failfast', 't',
  '\tconfig.queueBandEnable = (cbap_queue_band != 0);',
  '\tconfig.queueBandEnable = (cbap_queue_band != 0);\n'
  '\tconfig.queueBandV2Enable = (cbap_qb2_enable != 0);\n'
  '\tconfig.qb2BmaxRatio = cbap_qb2_bmax_ratio;\n'
  '\tconfig.qb2QTargetRatio = cbap_qb2_qtarget_ratio;\n'
  '\t// Fail-fast: v2 must be fully and consistently specified.  A screening\n'
  '\t// cell silently running with BMAX=0 would be indistinguishable from\n'
  '\t// "boost has no effect", so missing values are a hard config error.\n'
  '\tif (cbap_qb2_enable != 0){\n'
  '\t\tif (cbap_queue_band != 0)\n'
  '\t\t\tConfigError("CBAP_QUEUE_BAND_V2_ENABLE and CBAP_QUEUE_BAND_ENABLE "\n'
  '\t\t\t\t"are mutually exclusive");\n'
  '\t\tif (cbap_steady_cap == 0)\n'
  '\t\t\tConfigError("CBAP_QUEUE_BAND_V2_ENABLE requires "\n'
  '\t\t\t\t"CBAP_STEADY_CAP_ENABLE 1 (D4v2 = D3 + top-up)");\n'
  '\t\tif (!cbap_qb2_bmax_set ||\n'
  '\t\t\t\t!(cbap_qb2_bmax_ratio > 0.0 && cbap_qb2_bmax_ratio <= 0.10))\n'
  '\t\t\tConfigError("CBAP_QB2_BMAX_RATIO missing or outside (0, 0.10] "\n'
  '\t\t\t\t"(the old +0.30C policy is deliberately unreachable)");\n'
  '\t\tif (!cbap_qb2_qtarget_set ||\n'
  '\t\t\t\t!(cbap_qb2_qtarget_ratio > 0.0 && cbap_qb2_qtarget_ratio <= 0.5))\n'
  '\t\t\tConfigError("CBAP_QB2_QTARGET_RATIO missing or outside (0, 0.5]");\n'
  '\t\tif (cbap_qb2_trace_file.empty())\n'
  '\t\t\tConfigError("CBAP_QB2_TRACE_FILE required when "\n'
  '\t\t\t\t"CBAP_QUEUE_BAND_V2_ENABLE 1");\n'
  '\t}')

E('t6-file-open', 't',
  '\tif (!cbap_qc_trace_file.empty()){\n'
  '\t\tcbap_qc_trace_csv = fopen(cbap_qc_trace_file.c_str(), "w");',
  '\tif (!cbap_qb2_trace_file.empty()){\n'
  '\t\tcbap_qb2_trace_csv = fopen(cbap_qb2_trace_file.c_str(), "w");\n'
  '\t\tif (!cbap_qb2_trace_csv)\n'
  '\t\t\tConfigError("cannot open CBAP_QB2_TRACE_FILE");\n'
  '\t\tfprintf(cbap_qb2_trace_csv,\n'
  '\t\t\t"time_ns,generation,batch_active,queue_current_bytes,"\n'
  '\t\t\t"queue_predicted_bytes,pending_excess_bytes,arrival_wire_bps,"\n'
  '\t\t\t"service_wire_bps,base_target_bps,boost_requested_bps,"\n'
  '\t\t\t"boost_effective_bps,boost_lease_expire_ns,drain_bps,"\n'
  '\t\t\t"aggregate_requested_bps,aggregate_applied_bps,zone,veto_reason,"\n'
  '\t\t\t"background_applied_bps,incast_applied_bps\\n");\n'
  '\t}\n'
  '\tif (!cbap_qc_trace_file.empty()){\n'
  '\t\tcbap_qc_trace_csv = fopen(cbap_qc_trace_file.c_str(), "w");')

# ---- verify EVERY anchor across EVERY file BEFORE writing anything -------
src = {'h': h, 'c': c, 't': t}
bad = 0
for tag, which, old, new in edits:
    n = src[which].count(old)
    print('%-20s %s  count=%d %s' % (tag, which, n, 'OK' if n == 1 else 'FAIL'))
    if n != 1:
        bad += 1
if bad:
    print('')
    print('%d anchor(s) failed -- NOTHING written, tree untouched' % bad)
    sys.exit(2)

for tag, which, old, new in edits:
    src[which] = src[which].replace(old, new, 1)

io.open(HWH, 'w', encoding='utf-8', errors='surrogateescape').write(src['h'])
io.open(HWC, 'w', encoding='utf-8', errors='surrogateescape').write(src['c'])
io.open(T, 'w', encoding='utf-8', errors='surrogateescape').write(src['t'])
print('')
print('all %d edits applied atomically' % len(edits))
