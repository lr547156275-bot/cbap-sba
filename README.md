# CBAP-SBA

Sender-side Bandwidth Allocation for RDMA collective communication.

This repository contains everything needed to **reproduce** the experiments in
the paper: the simulator patch, every experiment configuration, the generators
that produced them, and the analysis scripts that turn raw output into the
reported tables.

Raw simulation output is **not** stored here (it is ~14 GB). It lives in the
companion archive repository as release assets — see [Data](#data).

---

## 1. What this is

CBAP-SBA plans the aggregate rate of a collective's flows *before* they are
released, instead of discovering the fair share through congestion feedback.
The comparison baselines are DCQCN, DCTCP, TIMELY, HPCC and a receiver-driven
direct-allocation control (DART-RA, see [§6](#6-dart-ra-baseline)).

## 2. Simulator

The simulator is the ns-3.17-era RoCE model from the
[HPCC repository](https://github.com/alibaba-edu/High-Precision-Congestion-Control).
This repo does **not** vendor it; you apply our patch on top.

```bash
git clone https://github.com/alibaba-edu/High-Precision-Congestion-Control hpcc
cd hpcc/simulation
git apply /path/to/cbap-sba/patches/dart-ra-and-cap2.patch
```

The patch is purely additive (207 insertions, 5 deletions across 3 files) and
introduces:

| Addition | Where | Purpose |
|---|---|---|
| `CC_MODE_DART_RA = 40` | `rdma-hw.h`, `rdma-hw.cc` | receiver-driven direct rate allocation baseline |
| `APP_RATE_CAP2_FLOW` / `_BPS` | `scratch/third.cc` | a second application-rate-cap group, so one scenario can hold two background flows at different loads |

Every insertion is mode-gated: no existing congestion-control path changes
behaviour. This was verified by a byte-identity regression gate — under the
patched binary the frozen CBAP and DCQCN results reproduce **byte for byte**
(19/19 and 11/11 output files respectively).

### Build

```bash
cd hpcc/simulation
CC=gcc CXX=g++ python2 ./waf configure --build-profile=debug \
    --cxxflags="-O0 -ggdb -g3 -std=gnu++11 -Wno-error=deprecated-declarations -fstrict-aliasing -Wstrict-aliasing"
python2 ./waf build
```

Notes that cost us time, so they are written down:

* waf 1.7.11 requires **python2.7**.
* Do **not** pass `--enable-examples --enable-tests`: `src/core/test` does not
  compile under modern GCC.
* The binary lands at `build/scratch/third` and is invoked as
  `build/scratch/third <config.txt>`.

## 3. Running an experiment

Every cell is one config file plus its scenario inputs:

```bash
export LD_LIBRARY_PATH=$PWD/build
build/scratch/third configs/v2_400g/fm400g_s2_cbap.txt
```

A config references four scenario input files that must sit where the config
says (`configs/<campaign>/` here):

| File | Contents |
|---|---|
| `*_flow.txt` | `src dst pg dport bytes start_time`, one row per flow |
| `*_sched.txt` | `flow_id round_id group_id participants bytes compute_gap jitter_ns jitter_group release_hint_ns` |
| `*_path.txt` | `flow_id n_links link_id…` — the bottleneck links each flow crosses |
| `*_link.txt` | `link_id node if capacity_bps ecn_threshold background_bps telemetry_eligible` |

Topologies (`configs/v2_400g/topo_*.txt`) are a 17-leaf / 4-spine fat tree,
4 hosts per leaf, at 10 / 100 / 200 / 400 Gb/s.

## 4. Campaigns

| Directory | Scenarios | Cells |
|---|---|---|
| `configs/v2_400g` | S0–S5 main matrix × {10, 200, 400} Gb/s × 5 algorithms | frozen reference campaign |
| `configs/s6dual` | S6 dual-bottleneck at 10/200/400 Gb/s | 18 |
| `configs/mdeep` | M1–M4 multi-bottleneck deepening at 400 Gb/s, 5 seeds | 120 |
| `configs/psweep200` | CBAP parameter sweeps (η, lease, BMAX) at 200 Gb/s S5 | 22 |
| `configs/ext` | E1 random arrival, E2 overlapping batches | 14 |
| `configs/s4match` | DCQCN-backend matching study on S4 @ 400 Gb/s | 3 |
| `configs/dart` | DART-RA across S0–S5 × 3 rates | 18 |
| `configs/v20` | cross-seed supplement batch | 120 |

Scenario shapes (main matrix): S0 = 64×256 KiB, S1 = 64×1 MiB, S2 = 64×4 MiB,
S3 = 64×16 MiB, S4 = S2 at 95 % background, S5 = 32×8 MiB; all with one
long-lived background flow per bottleneck starting at t = 2 ms and the
collective released at t = 20 ms.

## 5. Metric definitions

These are the definitions used by every table in the paper. They are
implemented in `scripts/*/summarize_*.py`.

* **CCT** = `max(last_ack_ns over collective members) − 20 ms`
  (20 ms is the common application-ready instant).
* **FCT** (per flow) = `last_ack_ns − first_data_tx_ns`.
* **p99** = nearest-rank, `sorted[ceil(0.99·N) − 1]`. At N = 32 or 64 this
  equals the maximum — stated explicitly because it is easy to misread.
* **Peak queue** = `round_summary.selected_link_peak_queue`, the continuous
  peak on the registered bottleneck. Do not substitute the sampled
  `qlen_ts` maximum; it reads systematically higher.
* **Queueing delay** = peak queue × 8 ÷ line rate.
* **PFC** = row count of `pfc_events.csv`.
* Collective membership comes from the schedule (`participant_count > 1`),
  never from a source-id heuristic. Background flows are excluded from CCT
  and FCT statistics.

## 6. DART-RA baseline

`CC_MODE 40` implements the **receiver-congestion half** of DART
(Xue et al., *DART: Divide and Specialize…*, IEEE/ACM ToN 2020) with an
**idealised control channel** (fixed delay, no bandwidth cost, never lost).

It is therefore an upper bound on that mechanism family, and it is **not**
a complete DART implementation. Not implemented: in-network deflection,
the reordering machinery deflection requires, DCQCN fallback, and congestion
location discrimination. `docs/dart-ra.md` lists this component by component.

Configuration keys: `DART_ALPHA`, `DART_ACTIVE_TIMEOUT_US`,
`DART_UPDATE_MIN_INTERVAL_US`, `DART_CTRL_DELAY_US`, `DART_ORACLE_N`,
`DART_MIN_RATE_MBPS`.

## 7. Analysis

```bash
python3 scripts/mdeep/summarize_m.py      # M campaign summary
python3 scripts/ext/summarize_ext.py      # E campaign summary
python3 scripts/psweep200/…               # parameter sweeps
```

Each reads the raw per-cell CSVs and emits the summary table. Point them at
an extracted archive (see below) to regenerate every number in the paper.

## 8. Data

Raw output is published as release assets on the archive repository:

> https://github.com/lr547156275-bot/cbap-sba-archive/releases

Each campaign is one `.tgz`. Extract next to this repo and run the analysis
scripts against it.

## 9. Reproducibility notes

* Seeds: `SIM_SEED` in each config. The main matrix uses seed 2; the M
  campaign carries seeds 1–5. `SIM_SEED 1` additionally requires the bounded
  packet-trace keys (`CBAP_PACKET_TRACE_FILE`, `CBAP_PACKET_TRACE_MAX_MB`)
  because of a guard in `third.cc`; this is logging-only and was proven
  behaviour-neutral by byte comparison.
* HPCC and TIMELY consume no randomness in this model: their cross-seed
  standard deviation is exactly 0.
* Forced-path cells (`FIXED_PATH_FILE`) show ~0.02 % run-to-run variation
  from ECMP tie-breaking; every other configuration reproduces byte-identically.

## 10. Licence and provenance

The upstream simulator is licensed by its authors; our patch and scripts are
provided for reproduction of the paper's results.
