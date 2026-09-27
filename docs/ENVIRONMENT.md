# Reproduction environment

What another machine needs in order to reproduce these experiments from the
published repositories.

## 1. Short answer

You need a **Linux x86_64 machine with Python 2.7 and GCC 9**. Python 2.7 is
the binding constraint — modern distributions no longer ship it — so the
recommended route is **Docker with `ubuntu:20.04`**, which is exactly what the
original experiments ran in.

| Resource | Minimum | Comfortable | Original |
|---|---|---|---|
| CPU | 2 cores | 4 cores | 4 vCPU (AMD EPYC 7763) |
| RAM | 4 GB | 8 GB | 15 GB |
| Disk | 5 GB | 20 GB | 32 GB |
| GPU | — | — | — |
| Network | only to clone/extract | | |

The simulator is single-threaded per run; more cores only let you run more
cells in parallel (the batch runners used 2–3 workers).

Wall-clock guidance: a full rebuild is roughly **20–40 minutes** on 4 cores
(clean ns-3 debug build, 39 modules); a single 400 Gb/s cell takes **1–10
minutes** depending on scenario size.

## 2. The exact original environment

Captured from the Codespace on 2026-09-27 before decommissioning.

```
Host VM     Ubuntu 24.04.4 LTS, kernel 6.8.0-1064-azure, x86_64
            4 vCPU AMD EPYC 7763, 15 GiB RAM, 32 GB disk
Container   ubuntu:20.04  (image id 8feb4d8ca535)
              Python 2.7.18
              gcc / g++ 9.4.0 (Ubuntu 9.4.0-1ubuntu1~20.04.2)
              GNU Make 4.2.1
              glibc 2.31 (Ubuntu GLIBC 2.31-0ubuntu9.17)
Build       waf 1.7.11  (version word 0x1070b00)
            --build-profile=debug
            CXXFLAGS = -O0 -ggdb -g3 -std=gnu++11
                       -Wno-error=deprecated-declarations
                       -fstrict-aliasing -Wstrict-aliasing
Binary      build/scratch/third, 5,549,832 bytes
            sha256 08482940442cb88942fe460d6312f2622c4eefb98fb92b7fd39cd48897e407db
            requires at most GLIBC_2.4
```

## 3. Recommended setup (Docker)

```bash
docker run -it --name cbap ubuntu:20.04 bash

# inside the container
apt-get update
apt-get install -y python2 python2.7 gcc-9 g++-9 make git wget \
                   build-essential pkg-config
ln -sf /usr/bin/python2.7 /usr/bin/python   # waf 1.7.11 invokes `python`
```

Then clone and build:

```bash
git clone https://github.com/alibaba-edu/High-Precision-Congestion-Control hpcc
cd hpcc/simulation
git apply /path/to/cbap-sba/patches/dart-ra-and-cap2.patch

python2 ./waf configure --build-profile=debug \
  --cxxflags="-O0 -ggdb -g3 -std=gnu++11 -Wno-error=deprecated-declarations -fstrict-aliasing -Wstrict-aliasing"
python2 ./waf build
```

`build/scratch/third` is the simulator. See the public repo README §2 for the
two build gotchas (`waf` needs python2.7; do not pass `--enable-examples
--enable-tests`).

### Alternative: native Ubuntu 20.04

Works identically on a bare-metal or VM install of Ubuntu 20.04 — the
container above is just `ubuntu:20.04` with those packages. Ubuntu 22.04 and
newer are **not** drop-in: they have no `python2` package, and GCC 12+ fails
on this codebase. If you must use a newer distro, run it through Docker or a
20.04 VM rather than fighting the toolchain.

## 4. What must be rebuilt, and why

**The published data does not include a runnable binary.** `third` is
dynamically linked against 36 `libns3.18-*-debug.so` libraries that live in
`build/`:

```
libns3.18-point-to-point-debug.so
libns3.18-network-debug.so
… 36 in total
```

Shipping `build/` (697 MB) would make the binary non-portable anyway, since it
bakes in the container's glibc and libstdc++. So the workflow is: **rebuild
from patched source, then run the published configs.**

After rebuilding, confirm you have a faithful environment by re-running the
frozen reference cells and comparing against the archive:

```bash
build/scratch/third configs/v2_400g/fm400g_s2_cbap.txt
# compare flow_timing.csv / round_summary.csv against
#   raw/v2_400g/results/fm400g_s2_cbap/  (from the v2_400g release asset)
```

These should match **byte for byte**. That is the byte-identity gate the
original campaigns used before trusting any new binary, and it is the single
most useful health check: if it passes, your environment is equivalent.

## 5. Data you need to fetch

| Source | What | Size |
|---|---|---|
| `cbap-sba` (public) | patch, all 1806 configs, scripts, summary tables | ~7 MB |
| `cbap-sba-archive` releases, `v2_400g.tgz` | frozen main matrix raw output — needed for the health check | 129 MB |
| other release assets | raw output for the remaining campaigns | 1.0–541 MB each |

The public repo alone is enough to **run** every experiment. The release
assets are needed to **compare against** the published results.

```bash
gh release download raw-data-v1 \
   -R lr547156275-bot/cbap-sba-archive \
   -p 'v2_400g.tgz'
tar xzf v2_400g.tgz
```

## 6. Practical notes

* **Runs are deterministic** for every configuration that does not use
  forced paths. Re-running a cell reproduces its CSVs byte-identically, so
  differences you see are real, not noise.
* The exception is `FIXED_PATH_FILE` cells (campaign `ext`, scenario E3 and
  the S6 variants), which showed ~0.02 % variation from ECMP tie-breaking.
* `SIM_SEED 1` requires the bounded packet-trace keys
  (`CBAP_PACKET_TRACE_FILE`, `CBAP_PACKET_TRACE_MAX_MB`) or the simulator
  refuses the config. Logging-only, proven behaviour-neutral.
* Batch runners (`scripts/*/run_*.sh`) are resumable and skip cells whose
  output is already marked done, so an interrupted campaign can be continued
  by re-running the same command.
* Peak disk during a campaign: the largest campaign (M, 144 cells) produced
  6.1 GB. Plan accordingly if you run everything.
