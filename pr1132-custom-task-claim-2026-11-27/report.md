# Custom-task claim (#1132) vs `main` — 2026-11-27

What the durable custom-task claim of nightBaker/fleans#1132 (fix for #818) costs under load. The claim
appends a `CustomTaskClaimed` event to the instance's journal before the dispatcher hands a task to a
worker, and renews it while the task runs; the only process in the suite that crosses that path on every
instance is `one-task` (start → one external `e2e-probe` task → end). `linear-10` (no custom task) is the
control; `long-diverse` has one custom task among ~45 nodes.

| | Fleans commit |
|---|---|
| `main` | `102cddf` (feat(editor): off switch for the Process assistant card, #1131) |
| `pr` | `b05c130` (#1132 head: `7ee90fe` + review fixes), parent `102cddf` |

## Summary

| | `main` (r1, r2) | `pr` (r1, r2) | Δ (mean) |
|---|---:|---:|---:|
| `one-task` at 50 /s — p99 | 0.270 s, 0.247 s | 0.281 s, 0.349 s | +22 % |
| `one-task` at 100 /s — p50 / p99 | 0.206 / 0.548 s, 0.181 / 0.425 s | 0.264 / 0.813 s, 0.251 / 0.818 s | **+33 % / +68 %** |
| `one-task` at 150 /s offered — completed /s | 136.8, 143.7 | 114.7, 115.9 | **−18 %** |
| `one-task` at 150 /s offered — starts rejected (r1) | 8.3 % | 21.7 % | ×2.6 |
| `one-task` at 200 /s offered — completed /s | 128.8, 138.8 | 122.7, 128.6 | −6 % |
| `one-task` at 100 /s — journal transactions per instance (Citus w1 + w2) | 5.6, 5.7 | 6.6, 6.5 | **+1.0** |
| `one-task` at 100 /s — journal WAL per instance (w1 + w2) | 1.8 KB, 1.8 KB | 3.3 KB, 3.3 KB | **+83 %** |
| `one-task` at 100 /s — CPU of the Citus workers (w1 + w2) | 28.4 %, 27.4 % | 35.4 %, 35.8 % | +29 % |
| `one-task` at 100 /s — CPU of `fleans-core` (3 silos) | 115 %, 118 % | 119 %, 118 % | +2 % |
| `linear-10` at 30 / 45 / 60 /s — p99 | 0.23 / 0.39 / 1.09 s, 0.22 / 0.79 / 1.17 s | 0.23 / 0.93 / 1.40 s, 0.26 / 0.42 / 1.54 s | within run-to-run noise |
| `long-diverse`, 40 VUs × 3 min — instances completed, end-to-end p95 | 1 855 / 5.20 s, 1 761 / 5.30 s | 1 857 / 4.96 s, 1 827 / 4.93 s | parity |
| Instances started and not completed, every scenario | 0 | 0 | — |
| Claim held / lost / claim-call-failed log lines (14515, 14517, 14518) | — | 0 | — |

- **The claim costs `one-task` about a sixth of its ceiling on this host.** Each custom task now makes a
  grain call and a journal append before the worker gets it: one more journal transaction per instance
  (+18 %), 83 % more journal WAL, ~29 % more CPU on the Citus workers. At 100 starts/s the p99 grows
  from ~0.49 s to ~0.82 s; at 150 starts/s offered the cluster completes ~115 /s instead of ~140 /s.
  Engine CPU (`fleans-core`) is unchanged, so the cost is the extra round trip and the extra write, not
  computation.
- **No renewals happened.** A one-task run takes ~50 ms of work, far below the 45 s lease, so every
  instance wrote exactly one claim event; renewals (one per `HeartbeatInterval` = 15 s while a task
  runs) add nothing here and only touch tasks that run for many seconds.
- **No correctness regression.** Every started instance completed in every round, on both builds; no
  claim was held, lost or failed to write. Apart from the scenario's intended `DivideByZeroException`
  error path (Worker silo) and two EF migration-history probes on a fresh database, no `fail`/`crit` log
  lines — the same counts on both builds.
- **Processes without custom tasks are unaffected.** `linear-10` stays within the run-to-run spread of
  this host (the 75 /s step is past the knee: `main` r2 queued up there while the other three rounds
  did not), and `long-diverse` completes the same number of instances with the same latencies.

## Setup

**Host:** cloud VM, Intel Xeon @ 2.10 GHz, **4 vCPU**, 15 GiB RAM, Linux 6.18, Docker 29.9 (cgroup
v1), k6 v2.4.0 on the same host — the host of [`dotnet11-vs-dotnet10-2026-11-13`](../dotnet11-vs-dotnet10-2026-11-13/report.md).
Compare the two builds with each other, not with the laptop reports.

**Stack:** `tests/load/docker-compose.yml` unchanged (nginx → 2 × `fleans-api`, 3 × `fleans-core`,
1 × `fleans-worker`, 2 × `external-worker`, Citus coordinator + 2 workers, Postgres + replica,
Postgres ops, Kafka), `FLEANS_CITUS_IMAGE=citusdata/citus:12.1`. Images from
`tests/load/build-images.sh` (`TAG=main` / `TAG=pr`) on .NET 11.0.

**Method:** four rounds on a fresh stack each, interleaved `main` r1 → `pr` r1 → `main` r2 → `pr` r2
to spread host drift over both builds ([`scripts/all.sh`](scripts/all.sh),
[`scripts/run-round.sh`](scripts/run-round.sh)):

1. `throughput-ceiling.sh`, `PROCESS=load-linear-10`, `RATES="30 45 60 75 90"`, 60 s pre-warm, then
   20 s warm-up + 60 s measured window per rate.
2. Same for `PROCESS=load-one-task`, `RATES="50 100 150 200"`, 30 s pre-warm.
3. `long-diverse.js`, `K6_PROFILE=constant K6_VUS=40 K6_DURATION=3m`.

Durations come from the read model (`CompletedAt − CreatedAt`); CPU is the `docker stats` average over
the measured window (% of one core, summed over replicas); transactions and WAL per instance from
`db-counters.sh`. The k6 `jslib` imports were replaced by local stand-ins as in the .NET 11 report
(jslib.k6.io is unreachable from this host).

## `one-task` ladder

| rate | build | round | completed /s | p50 | p95 | p99 |
|---:|---|---|---:|---:|---:|---:|
| 50 | main | r1 / r2 | 50.0 / 50.0 | 0.143 / 0.138 | 0.226 / 0.218 | 0.270 / 0.247 |
| 50 | pr | r1 / r2 | 50.0 / 50.0 | 0.149 / 0.151 | 0.232 / 0.245 | 0.281 / 0.349 |
| 100 | main | r1 / r2 | 99.8 / 100.0 | 0.206 / 0.181 | 0.402 / 0.315 | 0.548 / 0.425 |
| 100 | pr | r1 / r2 | 99.3 / 97.8 | 0.264 / 0.251 | 0.576 / 0.577 | 0.813 / 0.818 |
| 150 | main | r1 / r2 | 136.8 / 143.7 | 0.331 / 0.295 | 0.685 / 0.687 | 0.892 / 0.931 |
| 150 | pr | r1 / r2 | 114.7 / 115.9 | 0.415 / 0.318 | 0.782 / 0.655 | 0.989 / 0.900 |
| 200 | main | r1 / r2 | 128.8 / 138.8 | 0.352 / 0.330 | 0.700 / 0.725 | 0.924 / 0.979 |
| 200 | pr | r1 / r2 | 122.7 / 128.6 | 0.421 / 0.354 | 0.753 / 0.706 | 0.930 / 0.961 |

Past ~140 /s the API's admission limiter answers `429` to part of the starts (they create no
instance), so the percentiles at 150 and 200 /s describe the accepted instances only; the completed
rate is the comparison there.

Per-round files: `<round>-<build>/onetask/` and `linear10/` (`*-summary.txt`, `*.cpu.txt`,
`*.db.txt`), `long-diverse.summary.json`, `error-log-counts.txt`.

## What would win the cost back

Ideas for #1132, not measured here:

- Write the claim in the same journal batch as the instance's step that dispatches the task (the
  activity's `Executing` transition), instead of a separate dispatcher → instance call afterwards. That
  removes the extra round trip and the extra transaction; the event's bytes remain.
- Or keep the claim in the dispatcher grain's own state (one row per task, not in the instance journal):
  it does not grow the journal, but needs its own storage write.
