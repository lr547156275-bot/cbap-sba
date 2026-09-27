# Summary tables

These are the derived tables behind the paper's numbers. Each was produced by
the corresponding script in `../scripts/` from the raw per-cell CSVs.

| File | Campaign | Contents |
|---|---|---|
| `master_comparison.csv` | main matrix | S0–S5 × {10,200,400} Gb/s + S6 dual-bottleneck × {10,200,400}, 6 algorithms |
| `s6_dual_bottleneck.csv` | S6 | dual-bottleneck detail incl. per-side CCT and both bottleneck queue peaks |
| `m_summary.csv` | M1–M4 | multi-bottleneck deepening at 400 Gb/s, seed 2 |
| `m_crossseed.csv` | M1–M4 | the same cells aggregated over seeds 1–5 (mean / std / min / max) |
| `ext_summary.csv` | E1, E2 | random arrival and overlapping batches |
| `s4_backend_match.csv` | S4 | CBAP with the DCQCN baseline's backend constants vs the legacy ones |
| `param_sweep_200g_s5.csv` | S5 @ 200 Gb/s | η, lease and BMAX sweeps |

Columns follow the metric definitions in the top-level README §5.
Every value is single-seed unless the file name says otherwise.
