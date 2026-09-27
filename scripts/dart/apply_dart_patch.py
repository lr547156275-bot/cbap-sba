#!/usr/bin/env python3
"""Apply the DART-RA baseline patch (CC_MODE_DART_RA = 40) to the simulator.

Purely additive: three header declarations, one self-contained code block,
two mode-gated hooks (AddQueuePair, ReceiveUdp entry), config parsing in
third.cc.  Every insertion is anchored on an exact unique string and is
idempotent (re-running is a no-op).  No existing mode's code path is edited.
"""
import io, os, sys

SIM = "/work/simulation"

def patch(path, anchor, insert, before=False, tag=None):
    p = os.path.join(SIM, path)
    src = io.open(p, encoding="utf-8", errors="surrogateescape").read()
    marker = tag or insert[:60]
    if marker in src:
        print("  skip (already applied): %s :: %s" % (path, marker[:40]))
        return
    n = src.count(anchor)
    if n != 1:
        sys.exit("FATAL: anchor not unique (%d) in %s: %r" % (n, path, anchor[:80]))
    rep = (insert + anchor) if before else (anchor + insert)
    io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(
        src.replace(anchor, rep))
    print("  patched %s" % path)

H = "src/point-to-point/model/rdma-hw.h"
C = "src/point-to-point/model/rdma-hw.cc"
T = "scratch/third.cc"

print("== rdma-hw.h ==")
patch(H, "\t\tCC_MODE_CBAP_SBA_HPCC = 31\n\t};",
      "", before=False, tag="CC_MODE_DART_RA")  # placeholder replaced below
# enum entry: rewrite via explicit replace (comma insertion)
p = os.path.join(SIM, H)
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
if "CC_MODE_DART_RA" not in s:
    old = "\t\tCC_MODE_CBAP_SBA_HPCC = 31\n\t};"
    new = ("\t\tCC_MODE_CBAP_SBA_HPCC = 31,\n"
           "\t\t// DART-inspired receiver-driven direct allocation baseline\n"
           "\t\t// (receiver-congestion half only, idealised control channel).\n"
           "\t\tCC_MODE_DART_RA = 40\n\t};")
    assert s.count(old) == 1
    io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(
        s.replace(old, new))
    print("  patched enum CC_MODE_DART_RA")
else:
    print("  skip enum (present)")

patch(H, "\tstatic bool IsCbapMode(uint32_t mode);",
      "\n\tstatic void SetDartConfig(double alpha, uint64_t activeTimeoutNs,\n"
      "\t\tuint64_t minIntervalNs, uint64_t ctrlDelayNs, uint32_t oracleN,\n"
      "\t\tuint64_t minRateBps);\n"
      "\tstatic void DartDeliverRate(RdmaHw *hw, Ptr<RdmaQueuePair> qp,\n"
      "\t\tuint64_t bps);\n"
      "\tvoid DartOnReceiverData(CustomHeader &ch);",
      tag="SetDartConfig")

print("== rdma-hw.cc: DART block ==")
DART_BLOCK = """
// ===================== DART-RA baseline (CC_MODE_DART_RA = 40) ==============
// DART-inspired receiver-driven direct rate allocation.  Implements ONLY the
// receiver-congestion half of DART (Xue et al., ToN 2020): the receiver
// counts flows active on its access link inside a sliding window and assigns
// each an equal share of alpha * C_recv.  The allocation travels over an
// IDEALISED control channel: it is applied at the sender after a fixed delay,
// consumes no bandwidth and is never lost, which makes this baseline an
// upper bound on any real receiver-allocation implementation.  DART's
// in-network deflection half is NOT implemented.  No other CC mode reaches
// this code (all entry points are gated on CC_MODE_DART_RA).
struct DartCfg {
	double alpha;
	uint64_t activeTimeoutNs;
	uint64_t minIntervalNs;
	uint64_t ctrlDelayNs;
	uint64_t minRateBps;
	uint32_t oracleN;
};
static DartCfg s_dartCfg = {0.95, 100000, 10000, 6000, 100000000ULL, 0};
struct DartSenderRef {
	RdmaHw *hw;
	Ptr<RdmaQueuePair> qp;
	uint64_t lastSeenNs;
	uint64_t allocBps;
	DartSenderRef() : hw(NULL), qp(NULL), lastSeenNs(0), allocBps(0) {}
};
static std::map<uint64_t, DartSenderRef> s_dartSenders;
struct DartRecvState {
	uint64_t lastUpdateNs;
	std::map<uint64_t, uint64_t> lastSeen;   // flow key -> last data arrival
	DartRecvState() : lastUpdateNs(0) {}
};
static std::map<uint32_t, DartRecvState> s_dartRecv;   // by receiver node id

static uint64_t DartFlowKey(uint32_t sip, uint16_t sport, uint16_t dport){
	return ((uint64_t)sip << 32) | ((uint64_t)sport << 16) | (uint64_t)dport;
}

void RdmaHw::SetDartConfig(double alpha, uint64_t activeTimeoutNs,
		uint64_t minIntervalNs, uint64_t ctrlDelayNs, uint32_t oracleN,
		uint64_t minRateBps){
	s_dartCfg.alpha = alpha;
	s_dartCfg.activeTimeoutNs = activeTimeoutNs;
	s_dartCfg.minIntervalNs = minIntervalNs;
	s_dartCfg.ctrlDelayNs = ctrlDelayNs;
	s_dartCfg.oracleN = oracleN;
	s_dartCfg.minRateBps = minRateBps;
}

void RdmaHw::DartDeliverRate(RdmaHw *hw, Ptr<RdmaQueuePair> qp, uint64_t bps){
	if (!hw || !qp || qp->IsFinished())
		return;
	hw->ChangeRate(qp, DataRate(bps));
}

void RdmaHw::DartOnReceiverData(CustomHeader &ch){
	const uint64_t now = Simulator::Now().GetTimeStep();
	const uint64_t key = DartFlowKey(ch.sip, ch.udp.sport, ch.udp.dport);
	std::map<uint64_t, DartSenderRef>::iterator sit = s_dartSenders.find(key);
	if (sit == s_dartSenders.end())
		return;                       // not a registered DART sender
	DartRecvState &st = s_dartRecv[m_node->GetId()];
	st.lastSeen[key] = now;
	if (st.lastUpdateNs != 0 &&
			now - st.lastUpdateNs < s_dartCfg.minIntervalNs)
		return;
	st.lastUpdateNs = now;
	// receiver access-link capacity = the NIC this packet arrived on
	Ptr<RdmaRxQueuePair> rxQp = GetRxQp(ch.dip, ch.sip, ch.udp.dport,
		ch.udp.sport, ch.udp.pg, true);
	const uint32_t nic = GetNicIdxOfRxQp(rxQp);
	const uint64_t cap = m_nic[nic].dev->GetDataRate().GetBitRate();
	// count flows active within the sliding window
	uint32_t n = 0;
	for (std::map<uint64_t, uint64_t>::const_iterator it = st.lastSeen.begin();
			it != st.lastSeen.end(); ++it)
		if (now - it->second <= s_dartCfg.activeTimeoutNs)
			n++;
	if (n == 0)
		return;
	uint64_t alloc = (uint64_t)(s_dartCfg.alpha * (double)cap / (double)n);
	if (alloc < s_dartCfg.minRateBps)
		alloc = s_dartCfg.minRateBps;
	for (std::map<uint64_t, uint64_t>::const_iterator it = st.lastSeen.begin();
			it != st.lastSeen.end(); ++it){
		if (now - it->second > s_dartCfg.activeTimeoutNs)
			continue;
		std::map<uint64_t, DartSenderRef>::iterator fs =
			s_dartSenders.find(it->first);
		if (fs == s_dartSenders.end())
			continue;
		DartSenderRef &ref = fs->second;
		if (ref.allocBps == alloc)
			continue;                 // no change, no message
		ref.allocBps = alloc;
		Simulator::Schedule(NanoSeconds(s_dartCfg.ctrlDelayNs),
			&RdmaHw::DartDeliverRate, ref.hw, ref.qp, alloc);
	}
}

"""
patch(C, "void RdmaHw::AddQueuePair(", DART_BLOCK, before=True,
      tag="DART-RA baseline (CC_MODE_DART_RA")

print("== rdma-hw.cc: AddQueuePair hook ==")
patch(C,
      "\tDataRate m_bps = m_nic[nic_idx].dev->GetDataRate();\n"
      "\tqp->m_rate = m_bps;\n"
      "\tqp->m_max_rate = m_bps;",
      "\n\tif (m_cc_mode == CC_MODE_DART_RA){\n"
      "\t\t// register the sender so the receiver-side allocator can steer it\n"
      "\t\ts_dartSenders[DartFlowKey(sip.Get(), sport, dport)] =\n"
      "\t\t\tDartSenderRef();\n"
      "\t\tDartSenderRef &r = s_dartSenders[DartFlowKey(sip.Get(), sport,\n"
      "\t\t\tdport)];\n"
      "\t\tr.hw = this;\n"
      "\t\tr.qp = qp;\n"
      "\t\tif (s_dartCfg.oracleN > 0){\n"
      "\t\t\t// incast-group hint start (DART uses application-provided\n"
      "\t\t\t// group information); otherwise RoCE line-rate start\n"
      "\t\t\tuint64_t init = (uint64_t)(s_dartCfg.alpha *\n"
      "\t\t\t\t(double)m_bps.GetBitRate() / (double)s_dartCfg.oracleN);\n"
      "\t\t\tif (init < s_dartCfg.minRateBps)\n"
      "\t\t\t\tinit = s_dartCfg.minRateBps;\n"
      "\t\t\tqp->m_rate = DataRate(init);\n"
      "\t\t\tr.allocBps = init;\n"
      "\t\t}\n"
      "\t}",
      tag="register the sender so the receiver-side allocator")

print("== rdma-hw.cc: ReceiveUdp hook ==")
patch(C, "int RdmaHw::ReceiveUdp(Ptr<Packet> p, CustomHeader &ch){",
      "\n\tif (m_cc_mode == CC_MODE_DART_RA)\n"
      "\t\tDartOnReceiverData(ch);",
      tag="DartOnReceiverData(ch);")

print("== third.cc: config vars ==")
patch(T, "uint64_t cbap_packet_trace_rows = 0;",
      "double dart_alpha = 0.95;\n"
      "uint32_t dart_active_timeout_us = 100;\n"
      "uint32_t dart_update_min_interval_us = 10;\n"
      "uint32_t dart_ctrl_delay_us = 6;\n"
      "uint32_t dart_oracle_n = 0;\n"
      "uint64_t dart_min_rate_mbps = 100;\n",
      before=True, tag="dart_alpha")

print("== third.cc: config parsing ==")
PARSE = """			else if (key.compare("DART_ALPHA") == 0){
				conf >> dart_alpha;
				std::cout << "DART_ALPHA\\t\\t\\t" << dart_alpha << "\\n";
			}
			else if (key.compare("DART_ACTIVE_TIMEOUT_US") == 0){
				conf >> dart_active_timeout_us;
				std::cout << "DART_ACTIVE_TIMEOUT_US\\t\\t" << dart_active_timeout_us << "\\n";
			}
			else if (key.compare("DART_UPDATE_MIN_INTERVAL_US") == 0){
				conf >> dart_update_min_interval_us;
				std::cout << "DART_UPDATE_MIN_INTERVAL_US\\t" << dart_update_min_interval_us << "\\n";
			}
			else if (key.compare("DART_CTRL_DELAY_US") == 0){
				conf >> dart_ctrl_delay_us;
				std::cout << "DART_CTRL_DELAY_US\\t\\t" << dart_ctrl_delay_us << "\\n";
			}
			else if (key.compare("DART_ORACLE_N") == 0){
				conf >> dart_oracle_n;
				std::cout << "DART_ORACLE_N\\t\\t\\t" << dart_oracle_n << "\\n";
			}
			else if (key.compare("DART_MIN_RATE_MBPS") == 0){
				conf >> dart_min_rate_mbps;
				std::cout << "DART_MIN_RATE_MBPS\\t\\t" << dart_min_rate_mbps << "\\n";
			}
"""
patch(T, '\t\t\telse if (key.compare("CC_MODE") == 0){', PARSE, before=True,
      tag='DART_ALPHA") == 0')

print("== third.cc: apply config before seeding ==")
patch(T, "\tSeedManager::SetSeed(sim_seed);",
      "\tif (cc_mode == RdmaHw::CC_MODE_DART_RA)\n"
      "\t\tRdmaHw::SetDartConfig(dart_alpha,\n"
      "\t\t\t(uint64_t)dart_active_timeout_us * 1000ULL,\n"
      "\t\t\t(uint64_t)dart_update_min_interval_us * 1000ULL,\n"
      "\t\t\t(uint64_t)dart_ctrl_delay_us * 1000ULL,\n"
      "\t\t\tdart_oracle_n,\n"
      "\t\t\tdart_min_rate_mbps * 1000000ULL);\n",
      before=True, tag="RdmaHw::SetDartConfig")

print("PATCH COMPLETE")
