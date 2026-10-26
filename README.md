# Fleans load-test results

Reports from load runs of [Fleans](https://github.com/nightBaker/fleans). The stack, the k6 / Locust
scripts and the overrides live in [`tests/load/`](https://github.com/nightBaker/fleans/tree/main/tests/load)
of the Fleans repo; this repo keeps only what the runs produced. Every report names the Fleans commit it
measured. `#NNN` references are issues and PRs in `nightBaker/fleans`.

| Run | What it measures |
|---|---|
| [`target-arch-2026-10-24/`](target-arch-2026-10-24/report.md) | Road to 1.0.0 target architecture on a laptop: throughput ceilings, overload and admission control, timers, resource estimate vs Zeebe; scaling matrix in [`scaling-2026-10-24/`](scaling-2026-10-24) |
| [`local-2026-10-23/`](local-2026-10-23/report.md) | `main` before vs after the first Road-to-1.0 PRs (#888–#898): `long-diverse`, `linear-saturation`, `timers` |
| [`azure-2026-04-29/`](azure-2026-04-29/report.md) | Azure Container Apps + Azure Load Testing baseline |
| [`local/`](local/report.md) | First local Docker Compose baseline — 4 scenarios, bottleneck report |
| [`cloud/`](cloud/report.md) | Cloud validation template (phase 3) |

## Adding a run

1. Run from `tests/load` in a Fleans checkout; the scripts write to `tests/load/results/<run>/`
   (git-ignored there).
2. Copy the run directory here as `<name>-<YYYY-MM-DD>/` with a `report.md`: hardware, the Fleans
   commit, the commands, the tables.
3. Commit `<process>-summary.txt`, `capacity.md` and small text summaries. Leave out the per-rate
   `<process>-<rate>.*.txt` files and k6 CSVs — they are large and reproducible.
4. Add a row above; if the run changes the published numbers, update the Fleans website page
   `reference/load-testing.md` in a Fleans PR.
