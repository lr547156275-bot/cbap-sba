# -*- coding: utf-8 -*-
# Item 2: CBAP_QUEUE_BAND_ENABLE -- an independent switch for the queue-banded
#         boost/drain term.  Default 0 => byte-identical to D2/D3 behaviour.
#         The boost=0 forcing at rdma-hw.cc:938 is NOT deleted globally; it is
#         conditioned on the new flag only.
#         Q_abs/Q_low/Q_high/Q_red, MAX_BOOST, MIN_RATE and rho are untouched.
#
#         Necessary second edit: under steadyCapEnable the aggregate budget is
#         the static cap and effectivePlannerBudgetBps (which carries
#         boost-drain) is bypassed entirely (rdma-hw.cc:5124 vs 5126).  So
#         un-suppressing boost alone would provably change nothing.  The band is
#         therefore added to capWire in the WIRE domain, using
#         qcBoostEffectiveBps - qcDrainTargetBps directly rather than
#         controlDeltaBps (which was already converted to the PAYLOAD domain at
#         line 803 -- mixing them would re-introduce the 4.8% domain bug).
#         The demand bound min(demandWire, capWire) is preserved, so the target
#         still never exceeds what the flows can actually use.
#
# Item 3: a uniform first-data-transmit timestamp for EVERY cc_mode.
#         qp->cbap.firstDataTxNs is currently set inside the cbap.enabled guard
#         in PktSent, so DCQCN/HPCC never get it and no same-shaped FCT can be
#         built for the baselines.  Hoisted out of the guard: pure observability,
#         the field exists on every QP regardless of cbap.enabled.
#         Emitted into a NEW flow_timing.csv so no existing result file changes
#         schema and the byte-identity regression stays clean.
#         flow_summary.fct is NOT usable as a unified metric: start_time is
#         overridden to application_ready_ns for CBAP but is q->startTime for the
#         baselines, so that column is CCT for one algorithm and FCT for another.
import io
import sys

HWH = '/work/simulation/src/point-to-point/model/rdma-hw.h'
HWC = '/work/simulation/src/point-to-point/model/rdma-hw.cc'
T = '/work/simulation/scratch/third.cc'

h = io.open(HWH, encoding='utf-8', errors='surrogateescape').read()
c = io.open(HWC, encoding='utf-8', errors='surrogateescape').read()
t = io.open(T, encoding='utf-8', errors='surrogateescape').read()

if 'queueBandEnable' in h:
    print('already applied')
    sys.exit(0)

edits = []


def E(tag, which, old, new):
    edits.append((tag, which, old, new))


# ---------------- item 2 --------------------------------------------------
E('h-field', 'h',
  '\t\tdouble steadyCapFraction;  // 0.995 by default, not a tuning knob',
  '\t\tdouble steadyCapFraction;  // 0.995 by default, not a tuning knob\n'
  '\t\t// CBAP_QUEUE_BAND_ENABLE.  Default false keeps boost forced to 0 under\n'
  '\t\t// the steady cap (the D2/D3 arms).  True lets the queue-banded\n'
  '\t\t// boost(Q)/drain(Q) term participate in the aggregate target.\n'
  '\t\tbool queueBandEnable;')

E('h-init', 'h',
  '\t\t\t  steadyCapEnable(false), steadyCapFraction(0.995),',
  '\t\t\t  steadyCapEnable(false), steadyCapFraction(0.995),\n'
  '\t\t\t  queueBandEnable(false),')

E('c-boostgate', 'c',
  '\t\tif (s_cbapConfig.steadyCapEnable){\n'
  '\t\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\t}',
  '\t\t// queueBandEnable re-admits the boost term for the D4 arm only.  With\n'
  '\t\t// the flag off this is exactly the previous unconditional forcing.\n'
  '\t\tif (s_cbapConfig.steadyCapEnable && !s_cbapConfig.queueBandEnable){\n'
  '\t\t\truntime.qcBoostCommandedBps = 0;\n'
  '\t\t\truntime.qcBoostEffectiveBps = 0;\n'
  '\t\t}')

E('c-capwire', 'c',
  '\t\t\t\tconst long double capWire =\n'
  '\t\t\t\t\ts_cbapConfig.steadyCapFraction * (long double)cWire;',
  '\t\t\t\tlong double capWire =\n'
  '\t\t\t\t\ts_cbapConfig.steadyCapFraction * (long double)cWire;\n'
  '\t\t\t\t// Item 2: the static cap bypasses effectivePlannerBudgetBps, so the\n'
  '\t\t\t\t// queue band has to be applied here or it cannot reach the target.\n'
  '\t\t\t\t// WIRE domain on both sides -- qcBoost/qcDrain are wire rates,\n'
  '\t\t\t\t// unlike controlDeltaBps which is payload.\n'
  '\t\t\t\tif (s_cbapConfig.queueBandEnable){\n'
  '\t\t\t\t\tconst long double dWire =\n'
  '\t\t\t\t\t\t(long double)lit->second.qcBoostEffectiveBps\n'
  '\t\t\t\t\t\t- (long double)lit->second.qcDrainTargetBps;\n'
  '\t\t\t\t\tcapWire += dWire;\n'
  '\t\t\t\t\tif (capWire < 0.0L)\n'
  '\t\t\t\t\t\tcapWire = 0.0L;\n'
  '\t\t\t\t}')

E('t-global', 't',
  'double cbap_steady_cap_fraction = 0.995;',
  'double cbap_steady_cap_fraction = 0.995;\n'
  'uint32_t cbap_queue_band = 0;          // CBAP_QUEUE_BAND_ENABLE, default off')

E('t-assign', 't',
  '\tconfig.steadyCapFraction = cbap_steady_cap_fraction;',
  '\tconfig.steadyCapFraction = cbap_steady_cap_fraction;\n'
  '\tconfig.queueBandEnable = (cbap_queue_band != 0);')

E('t-parse', 't',
  '\t\t\telse if(key.compare("CBAP_STEADY_CAP_ENABLE")==0){',
  '\t\t\telse if(key.compare("CBAP_QUEUE_BAND_ENABLE")==0){\n'
  '\t\t\t\tconf>>cbap_queue_band;\n'
  '\t\t\t\tstd::cout << "CBAP_QUEUE_BAND_ENABLE\\t\\t" << cbap_queue_band << "\\n";\n'
  '\t\t\t}\n'
  '\t\t\telse if(key.compare("CBAP_STEADY_CAP_ENABLE")==0){')

# ---------------- item 3 --------------------------------------------------
E('c-firsttx', 'c',
  '\tqp->lastPktSize = pkt->GetSize();\n'
  '\tif (qp->cbap.enabled){',
  '\tqp->lastPktSize = pkt->GetSize();\n'
  '\t// Item 3: the unified FCT needs the first data transmit for EVERY cc_mode,\n'
  '\t// not just CBAP.  This field is plain observability and is present on every\n'
  '\t// QP whether or not cbap.enabled, so it is safe to stamp outside the guard.\n'
  '\t// GetTimeStep() to match the units the rest of PktSent already uses.\n'
  '\tif (qp->cbap.firstDataTxNs == 0)\n'
  '\t\tqp->cbap.firstDataTxNs = Simulator::Now().GetTimeStep();\n'
  '\tif (qp->cbap.enabled){')

E('t-ft-global', 't',
  'FILE *flow_summary_csv = NULL, *round_summary_csv = NULL;',
  'FILE *flow_summary_csv = NULL, *round_summary_csv = NULL;\n'
  'FILE *flow_timing_csv = NULL;\n'
  'std::string flow_timing_file;')

E('t-ft-parse', 't',
  '\t\t\telse if(key.compare("FLOW_SUMMARY_FILE")==0) conf>>flow_summary_file;',
  '\t\t\telse if(key.compare("FLOW_SUMMARY_FILE")==0) conf>>flow_summary_file;\n'
  '\t\t\telse if(key.compare("FLOW_TIMING_FILE")==0) conf>>flow_timing_file;')

E('t-ft-open', 't',
  '\tif(!round_summary_file.empty()){\n'
  '\t\tround_summary_csv=fopen(round_summary_file.c_str(),"w");',
  '\t// Item 3: one row per completed flow with the raw timestamps needed to\n'
  '\t// build FCT/BCT/CCT identically for CBAP and for the baselines.  Written\n'
  '\t// for every cc_mode.  application_ready/network_release are 0 when the\n'
  '\t// algorithm has no admission stage, which is a fact about the algorithm.\n'
  '\tif(!flow_timing_file.empty()){\n'
  '\t\tflow_timing_csv=fopen(flow_timing_file.c_str(),"w");\n'
  '\t\tif(!flow_timing_csv)ConfigError("cannot open FLOW_TIMING_FILE");\n'
  '\t\tfprintf(flow_timing_csv,"scenario,algorithm,seed,flow_id,src,dst,'
  'total_size_bytes,app_start_ns,first_data_tx_ns,last_ack_ns,'
  'application_ready_ns,network_release_ns,acked_bytes\\n");\n'
  '\t}\n'
  '\tif(!round_summary_file.empty()){\n'
  '\t\tround_summary_csv=fopen(round_summary_file.c_str(),"w");')

E('t-ft-emit', 't',
  '\t\t\tfflush(flow_summary_csv);\n'
  '\t\t}\n'
  '\t\tbreak;',
  '\t\t\tfflush(flow_summary_csv);\n'
  '\t\t}\n'
  '\t\tif(flow_timing_csv){\n'
  '\t\t\tuint64_t readyNs=0, releaseNs=0;\n'
  '\t\t\tif(q->crfm.enabled && !q->crfm.rounds.empty()){\n'
  '\t\t\t\treleaseNs=q->crfm.rounds.front().releaseTimeNs;\n'
  '\t\t\t\tuint64_t r=0;\n'
  '\t\t\t\tif(RdmaHw::GetCbapScopeApplicationReadyNs(\n'
  '\t\t\t\t\t\tq->crfm.rounds.front().roundGroupId,r))\n'
  '\t\t\t\t\treadyNs=r;\n'
  '\t\t\t}\n'
  '\t\t\tfprintf(flow_timing_csv,"%s,%s,%u,%u,%u,%u,%lu,%lu,%lu,%lu,%lu,%lu,%lu\\n",\n'
  '\t\t\t\tscenario_name.c_str(),algorithm_name.c_str(),sim_seed,\n'
  '\t\t\t\texperiment_flows[i].id,sid,did,q->m_size,\n'
  '\t\t\t\t(uint64_t)q->startTime.GetNanoSeconds(),\n'
  '\t\t\t\tq->cbap.firstDataTxNs,\n'
  '\t\t\t\t(uint64_t)Simulator::Now().GetNanoSeconds(),\n'
  '\t\t\t\treadyNs,releaseNs,q->snd_una);\n'
  '\t\t\tfflush(flow_timing_csv);\n'
  '\t\t}\n'
  '\t\tbreak;')

# ---- verify EVERY anchor across EVERY file BEFORE writing anything -------
src = {'h': h, 'c': c, 't': t}
bad = 0
for tag, which, old, new in edits:
    n = src[which].count(old)
    print('%-14s %s  count=%d %s' % (tag, which, n, 'OK' if n == 1 else 'FAIL'))
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
