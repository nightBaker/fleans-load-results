# .NET 11 vs .NET 10 — 2026-11-13

The same Fleans code, the same load stack and the same scenarios on the .NET 10 and .NET 11 runtimes:
throughput ladders for the roadmap's headline processes (`linear-10`, `one-task`), the long, diverse
process (`long-diverse`), then the rest of the suite — `timers-1m`, `signal-fanout`, `long-lived`,
`mi-fanout`, the classic `linear` / `parallel` / `events` / `mixed` scripts — and a 30-minute soak at the
roadmap's 5 + 30 minute method; memory, startup and image size. The .NET 11 build is the migration in
nightBaker/fleans branch `claude/dotnet-11-migration-load-testing-bnfddd` (`24ec1b7`); the .NET 10
build is its parent, `main` at `a50fcfe` (release prep v0.13.0). The only difference between the two
builds is the target framework, the SDK, `Microsoft.AspNetCore.*` / `Microsoft.Extensions.*` 11.0.0
and the base image.

## Summary

| | .NET 10 (10.0.15) | .NET 11 (11.0.0) | Δ |
|---|---:|---:|---:|
| `linear-10` at 30 / 45 /s — p99 | 0.166 s / 0.304 s | **0.106 s / 0.244 s** | −36 % / −20 % |
| `linear-10` at 30 / 45 /s — CPU of the Fleans processes | 126 % / 152 % | **105 % / 130 %** | −16 % / −14 % |
| `linear-10` at 75 /s (≈ ceiling) — p50 / p99 | 0.354 s / 1.097 s | **0.217 s / 0.930 s** | −39 % / −15 % |
| `one-task` at 50 / 100 /s — CPU of the Fleans processes | 130 % / 180 % | **107 % / 162 %** | −17 % / −10 % |
| `one-task` at 100 /s — p99 | 0.376 s | **0.313 s** | −17 % |
| `one-task` at 200 /s offered (past the ceiling) — accepted and completed | 168.9 /s | **179.6 /s** | +6 % |
| `long-diverse`, 40 VUs, fresh stack — throughput, end-to-end p95 | 12.40 /s, 4.08 s | 12.41 /s, 4.09 s | parity |
| `long-diverse` — CPU of `fleans-core` | 106 % | **101 %** | −5 % |
| **Soak**: `linear-10` at 45 /s for 30 min — p99, CPU of the Fleans processes | 0.293 s, 152 % | **0.260 s, 135 %** | −11 % / −11 % |
| Classic `linear` / `parallel` / `mixed` (500 / 500 / 100 VUs, overload) — instances completed | 19 410 / 19 194 / 19 962 | **21 996 / 22 379 / 22 237** | +13 / +17 / +11 % |
| Classic `events` (200 VUs, overload) — instances completed | 2 426 | 2 305 | −5 % |
| `mi-fanout` 1 000 branches — all messages delivered in (r1, r2) | 26.9 s, 28.5 s | **20.2 s, 22.0 s** | −24 % |
| `timers-1m` 10 000 timers / `signal-fanout` 10 000 / `long-lived` 10 000 waiting | all fired / all received / PASS | all fired / all received / PASS | — |
| Peak memory, `fleans-core` (per silo) | 361 MiB | 384 MiB | +6 % |
| Image size, `fleans-api` (compressed) | 167 MB | 181 MB | +14 MB |
| Correctness: unit + integration / Postgres / Kafka suites | — | 2 111 / 370 / 10 passed, 0 failed | — |

- **.NET 11 is the better runtime for Fleans on this hardware.** At the same start rate the engine
  processes (Core silos, API, Worker silo, gRPC workers) use **4–17 % less CPU** — the most at
  moderate load (−14 to −17 % at 30–50 /s), where per-request overhead dominates; near saturation
  the stack is bound by the databases and Kafka (unchanged), so the gap narrows to 4–7 %.
  `linear-10` process duration is **12–46 % lower at p50 and 11–36 % lower at p99** at every rate;
  `one-task` (most of whose time is the worker's 50 ms and the gRPC round trips) is within ±3 %
  except at 100 /s (p99 −17 %), and past its ceiling .NET 11 accepted 6 % more starts.
- **No regression in behaviour.** Every instance that was started completed (a start answered with
  `429` creates none), in both runtimes, in
  every round; no `fail`/`crit` log lines apart from the scenario's intended `DivideByZeroException`
  error path and two EF migration-history probes on a fresh database (identical in both).
- **Memory is about the same**: +6 % peak on Core silos, −4 % on the Worker silo, the API and the
  external worker unchanged. The .NET 11 image is 14 MB larger compressed — the `aspnet:11.0` base
  moved from Ubuntu 24.04 to 26.04.
- **The rest of the suite agrees and finds no regression.** Over 30 minutes at 45 starts/s
  (81 000 instances each, 0 failed) .NET 11 used 11 % less CPU in the engine processes, with p99
  0.260 s against 0.293 s. Under the classic scripts' heavy overload it completed 11–17 % more
  instances in the same 5 minutes (`events`: −5 %, a single run). Timers, signal broadcasts,
  long-lived waits and multi-instance fan-out kept every instance, in two rounds each; their latencies
  are on par or better on .NET 11 (`mi-fanout` delivery −24 %, broadcast answered 683–874 ms against
  878–1 198 ms).
- **Startup is unchanged**: the whole stack is healthy in 36–37 s with either runtime.
- `long-diverse` is a closed-loop scenario dominated by its 1 s timers and client round trips, so its
  throughput is set by the VUs, not the CPU: both runtimes give the same result, with ~5 % less
  engine CPU on .NET 11. The 429 bursts seen in the `long-diverse` step of the full rounds are the
  admission limiter, not the runtime ([§ 429s at the start of `long-diverse`](#429s-at-the-start-of-long-diverse)).

## Setup

**Host:** cloud VM, Intel Xeon @ 2.10 GHz, **4 vCPU**, 15 GiB RAM, no swap, Linux 6.18, Docker 29.9
(cgroup v1, overlayfs). k6 v2.4.0 on the same host. Nothing else running during the runs. This is
less than half the CPU of the laptop the stack is sized for (10 CPU), so the ceilings are lower than in
[`target-arch-2026-10-24`](../target-arch-2026-10-24/report.md); compare the two runtimes with each
other, not with that report.

**Stack:** `tests/load/docker-compose.yml` unchanged — nginx → 2 × `fleans-api` (Api role), 3 ×
`fleans-core`, 1 × `fleans-worker`, 2 × `external-worker` (gRPC, serves `e2e-probe`), Citus coordinator
\+ 2 workers (journal, 32 shards), Postgres read model + streaming replica, Postgres ops (membership +
reminders), Kafka. CPU split by `cpu_shares`, no `cpus` caps. `FLEANS_CITUS_IMAGE=citusdata/citus:12.1`
(amd64 host, so the upstream image instead of the source build).

**Builds** (`dotnet publish -c Release` + `mcr.microsoft.com/dotnet/aspnet:<major>` as in
`tests/load/build-images.sh`):

| | .NET 10 | .NET 11 |
|---|---|---|
| Fleans commit | `a50fcfe` (`main`, v0.13.0) | `24ec1b7` (migration branch) |
| SDK / runtime | 10.0.404 / 10.0.15 | 11.0.100 / 11.0.0 |
| Base image | `aspnet:10.0`, Ubuntu 24.04 | `aspnet:11.0`, Ubuntu 26.04 |
| Image `fleans-api` / `fleans-worker` / `fleans-external-worker`, compressed | 167 / 165 / 99 MB | 181 / 180 / 114 MB |
| EF Core / Npgsql EF | 10.0.5 / 10.0.1 | 10.0.5 / 10.0.1 (unchanged, see the migration commit) |
| Orleans | 10.4.0 | 10.4.0 |

**Method.** Two full rounds per runtime, alternating `net10 → net11 → net10 → net11`, each on a
fresh stack (`docker compose down -v`, `up -d --wait`, `setup.js`):

1. `throughput-ceiling.sh`, `PROCESS=load-linear-10`, `RATES="30 45 60 75 90"`, 60 s pre-warm, then
   per rate 20 s warm-up + **1 min** measured window at a constant start rate (open model).
2. Same for `PROCESS=load-one-task`, `RATES="50 100 150 200"`, 30 s pre-warm.
3. `long-diverse.js`, 40 constant VUs for 3 min.

Then two more rounds per runtime of `long-diverse` alone on a fresh stack (30 s warm-up at 10 VUs,
then 40 VUs for 4 min), because step 3 starts right after the overload step of `one-task`
([§ 429s](#429s-at-the-start-of-long-diverse)).

**Rest of the suite** — every scenario on a fresh stack, `net10` then `net11` back to back
(`scripts/run-suite.sh`), sized for this host by the README's own guidance:

| scenario | settings | rounds |
|---|---|---:|
| `timers-1m.js` | `K6_TIMERS_COUNT=10000 K6_TIMERS_RATE=100`, `timers-1m-lag.sql` 4 min after arming | 2 |
| `signal-fanout.js` | `K6_FANOUT_COUNT=10000 K6_FANOUT_RATE=100 K6_WINDOW_S=60`, linear-10 at 20/s | 2 |
| `long-lived.js` | `K6_PARK_COUNT=10000 K6_PARK_RATE=100 K6_WINDOW_S=60 K6_WARMUP_S=30`, 20 VUs | 2 |
| `mi-fanout.js` | `K6_MI_SIZES=100,500,1000` | 2 |
| `linear.js`, `parallel.js`, `events.js`, `mixed.js` | the scripts' own profiles (500 / 500 / 200 / 40 + 30 + 30 VUs, 1 + 3 + 1 min) | 1 |
| soak | `throughput-ceiling.sh`, `RATES=45 PROCESS=load-linear-10 PREWARM=5m WARMUP=30s DURATION=30m` | 1 |

Latency of the throughput ladders comes from the read model (`CompletedAt − CreatedAt`, both journal
timestamps), so neither k6 nor polling adds to it. CPU is the `docker stats` average over the measured
window, in % of one core, summed over containers (the host has 400 %). "Fleans processes" =
`fleans-core` + `fleans-api` + `fleans-worker` + `external-worker`; the rest is Citus, Postgres,
Kafka and nginx.

The driver scripts are in [`scripts/`](scripts/): `run-round.sh` (one full round), `run-ld.sh` (the
isolated `long-diverse` round), `compare.py` / `compare-ld.py` (the tables below, also saved as
[`tables-throughput-rounds.md`](tables-throughput-rounds.md) and
[`tables-long-diverse-isolated.md`](tables-long-diverse-isolated.md)), `run-suite.sh` / `compare2.py` for
the rest of the suite ([`tables-suite.md`](tables-suite.md), raw summaries in [`suite/`](suite/)).
`jslib.k6.io` was unreachable
from the test host, so `long-diverse.js`, `events.js` and `long-lived.js` ran from a copy whose two `jslib` imports point at local
stand-ins (`scripts/k6-utils.js`: `uuidv4` = `crypto.randomUUID`; `scripts/k6-summary.js`: a plain-text
`textSummary`) and which logs the status of a failed start. The JSON summaries are k6's own.

## Results

### `linear-10` — 10 script tasks in a row

Mean of the two rounds. Every instance started in the window completed, 0 failed, 0 HTTP errors,
0 dropped iterations, in every round of both runtimes.

| offered /s | completed /s .NET 10 / 11 | .NET 10 p50 / p95 / p99 (s) | .NET 11 p50 / p95 / p99 (s) | Δ p50 | Δ p99 | CPU total .NET 10 / 11 | Δ |
|---:|---|---|---|---:|---:|---|---:|
| 30 | 30.0 / 30.0 | 0.043 / 0.105 / 0.166 | **0.038 / 0.075 / 0.106** | −12 % | −36 % | 229 / 203 % | −11 % |
| 45 | 45.0 / 45.0 | 0.071 / 0.223 / 0.304 | **0.045 / 0.154 / 0.244** | −37 % | −20 % | 273 / 244 % | −11 % |
| 60 | 59.8 / 60.0 | 0.168 / 1.189 / 1.896 | **0.090 / 0.780 / 1.683** | −46 % | −11 % | 307 / 288 % | −6 % |
| 75 | 75.0 / 75.0 | 0.354 / 0.863 / 1.097 | **0.217 / 0.692 / 0.930** | −39 % | −15 % | 329 / 316 % | −4 % |
| 90 | 90.0 / 90.0 | 3.011 / 5.927 / 7.043 | **2.605 / 4.728 / 5.835** | −13 % | −17 % | 343 / 331 % | −3 % |

Per round, p50 / p99 (s):

| offered /s | r1 .NET 10 | r1 .NET 11 | r2 .NET 10 | r2 .NET 11 |
|---:|---|---|---|---|
| 30 | 0.046 / 0.201 | 0.040 / 0.120 | 0.040 / 0.130 | 0.035 / 0.093 |
| 45 | 0.087 / 0.365 | 0.054 / 0.265 | 0.056 / 0.244 | 0.037 / 0.224 |
| 60 | 0.228 / 2.500 | 0.116 / 1.088 | 0.107 / 1.292 | 0.065 / 2.277 |
| 75 | 0.369 / 1.218 | 0.314 / 1.292 | 0.338 / 0.976 | 0.121 / 0.568 |
| 90 | 5.330 / 12.340 | 4.930 / 9.931 | 0.693 / 1.745 | 0.280 / 1.739 |

The sustained ceiling at p99 < 1 s is ~45 /s with either runtime on 4 vCPU (60 /s already has
second-long tails in some rounds); 90 /s is past it — the queue builds up and drains after the
window. p50 is lower on .NET 11 in all 10 pairs; p99 in 8 of 10. Above ~60 /s the host is at
75–85 % CPU and single rounds are noisy (compare r1 and r2 at 90 /s), so read the high rates as a
trend.

CPU per completed instance and where it goes:

| offered /s | CPU ms / instance, whole stack .NET 10 / 11 | Δ | Fleans processes .NET 10 / 11 (% of a core) | Δ | Fleans processes, CPU ms / instance | databases + Kafka + nginx .NET 10 / 11 |
|---:|---|---:|---|---:|---|---|
| 30 | 76.5 / 67.7 | −11 % | 126 / 105 | −16 % | 41.9 / 35.1 | 104 / 98 % |
| 45 | 60.7 / 54.2 | −11 % | 152 / 130 | −14 % | 33.8 / 29.0 | 121 / 113 % |
| 60 | 51.4 / 48.1 | −6 % | 164 / 152 | −8 % | 27.5 / 25.3 | 143 / 137 % |
| 75 | 43.9 / 42.1 | −4 % | 168 / 159 | −5 % | 22.4 / 21.2 | 161 / 157 % |
| 90 | 38.1 / 36.8 | −4 % | 173 / 161 | −7 % | 19.3 / 17.9 | 170 / 170 % |

Per service at 45 /s: `fleans-core` (3 silos) 104 → 87 %, `fleans-worker` 37 → 35 %, `fleans-api`
(2) 10 → 8 %. The database tier does the same work on both runtimes — committed transactions / WAL
KB per completed instance (`db-counters.sh`), r1 and r2:

| | `postgres` (read model) | `citus-w1` | `citus-w2` |
|---|---|---|---|
| `linear-10` 45 /s, .NET 10 | 2.2 / 5.4, 2.2 / 5.3 | 7.2 / 3.1, 7.0 / 3.0 | 7.2 / 3.1, 7.3 / 3.2 |
| `linear-10` 45 /s, .NET 11 | 2.3 / 5.3, 2.2 / 5.2 | 7.2 / 3.2, 7.3 / 3.2 | 7.1 / 3.1, 6.9 / 3.1 |
| `one-task` 100 /s, .NET 10 | 1.8 / 2.3, 1.8 / 2.5 | 2.9 / 0.9, 2.9 / 1.0 | 2.8 / 0.9, 2.8 / 0.9 |
| `one-task` 100 /s, .NET 11 | 1.8 / 2.3, 1.8 / 2.4 | 2.9 / 0.9, 2.8 / 0.9 | 2.8 / 0.9, 2.8 / 0.9 |

so the database CPU moves only with how many instances a window completes.

### `one-task` — one external `e2e-probe` task on the gRPC workers (50 ms of task work)

Mean of the two rounds; 0 failed and 0 unfinished in every round.

| offered /s | completed /s .NET 10 / 11 | .NET 10 p50 / p95 / p99 (s) | .NET 11 p50 / p95 / p99 (s) | Δ p99 | CPU total .NET 10 / 11 | Fleans processes .NET 10 / 11 | Δ |
|---:|---|---|---|---:|---|---|---:|
| 50 | 50.0 / 50.0 | 0.136 / 0.215 / 0.242 | **0.135 / 0.210 / 0.234** | −3 % | 216 / 192 % | 130 / 107 % | −17 % |
| 100 | 99.8 / 100.0 | 0.169 / 0.282 / 0.376 | **0.158 / 0.251 / 0.313** | −17 % | 301 / 281 % | 180 / 162 % | −10 % |
| 150 | 148.6 / 149.4 | 0.263 / 0.549 / 0.730 | **0.223 / 0.489** / 0.738 | +1 % | 326 / 319 % | 186 / 179 % | −4 % |
| 200 | 168.9 / **179.6** | 0.310 / 0.613 / 0.798 | **0.299 / 0.597 / 0.785** | −2 % | 332 / 326 % | 189 / 180 % | −5 % |

At 200 /s both runtimes are past the ceiling (~170–180 /s here): k6 sends 200 /s, the admission limiter
answers part of the starts with `429` and the rest complete with p99 < 1 s — the designed overload
behaviour. Starts shed: .NET 10 20.9 % / 10.5 %, .NET 11 9.0 % / 12.2 % (r1 / r2). CPU per
completed instance at 200 /s: 19.6 → 18.2 ms (−7 %). The gRPC workers' CPU went 14 → 10 % and
the API's 29 → 27 %.

### `long-diverse` — ~45 nodes, 4 client interactions, external task, timers

Isolated rounds (fresh stack, 30 s warm-up at 10 VUs, then 40 VUs × 4 min), mean of two rounds:

| | .NET 10 | .NET 11 | Δ |
|---|---:|---:|---:|
| completed iterations /s | 12.40 | 12.41 | +0.1 % |
| instances completed per round | 2 930 | 2 988 | +2.0 % |
| completed / started | 0.972 | 0.991 | |
| end-to-end med / p95 | 3 120 / 4 082 ms | 3 060 / 4 086 ms | −1.9 % / +0.1 % |
| engine duration med / p95 | 2 849 / 3 782 ms | 2 801 / 3 800 ms | −1.7 % / +0.5 % |
| start request med / p95 | 50.8 / 150.5 ms | 51.2 / 156.5 ms | +0.7 % / +4.0 % |
| all HTTP requests med / p95 | 17.9 / 106.7 ms | 18.6 / 107.6 ms | +3.8 % / +0.8 % |
| CPU, whole stack | 299 % | 298 % | −0.3 % |
| CPU, `fleans-core` ×3 / `fleans-api` ×2 / `fleans-worker` | 106 / 32 / 33 % | **101 / 30 / 32 %** | −5 / −6 / −4 % |
| peak memory per container, `fleans-core` / `fleans-api` / `fleans-worker` | 281 / 158 / 274 MiB | 287 / 163 / 298 MiB | +2 / +3 / +9 % |

Every started instance that k6 followed reached its end with the expected path (`ld_path_mismatch`
0, `ld_instance_failed` 0, `ld_poll_stall` 0, `correlation_miss` 0) in every round. Each iteration
waits on two 1 s timers and four client steps, so the scenario measures latency under a fixed client
population, not CPU; here the runtimes are equal within the round-to-round spread (±3 %).

#### 429s at the start of `long-diverse`

In the full rounds, `long-diverse` starts 40 VUs at once right after `one-task` at 200 /s, which has
pushed the admission limit down to 8–12 per API replica (`Admission limit lowered … to N` in the
logs). An idle limit does not grow, so the burst of 40 simultaneous starts finds ~16–20 slots; every
VU that gets a `429` ends its iteration at once and starts the next, which turns into a storm of
fast `429`s for about a second. In the full rounds it hit .NET 11 (r1: 785 starts, r2: 378) and not
.NET 10; in the isolated rounds, with no prior overload, it hit both — .NET 10 ld2: 153 starts,
.NET 11 ld2: 46 (ld1: 8 and 7). The failed starts carry `{"error":"The cluster is at its admission
limit. Retry later."}` and none of them is lost work: the steady state after the first second shows
0 errors in all rounds, and the full-round steady state was 12.4–12.5 iterations/s on .NET 11 against
11.4–12.1 /s on .NET 10. It is a property of the scenario (no back-off after a `429`) and of the
limiter (no growth while idle), the same on both runtimes.

### Rest of the suite

#### Classic scenarios (`linear`, `parallel`, `events`, `mixed` — the scripts' own VU profiles)

Closed model at the scripts' default VU counts (500 / 500 / 200 / 40+30+30 VUs, 5 min with ramps) — far above this host's ceiling, so the admission limiter answers most starts with `429`; the scenario measures how much work each runtime gets through under that overload. Completed instances and process duration from the read model (`throughput.sql`), CPU = `docker stats` average over the k6 run.

| scenario | runtime | completed | completed /s (peak 10 s) | process p50 / p99 (s) | requests /s | `429` / failed | start p95 (ms) | CPU Fleans / total (%) |
|---|---|---:|---|---|---:|---:|---:|---|
| `linear` | .NET 10 | 19410 | 65.0 (121.5) | 0.399 / 1.703 | 2 339 | 97.2 % | 213 | 143 / 255 |
|  | .NET 11 | 21996 | 73.6 (117.3) | 0.372 / 2.057 | 2 222 | 96.7 % | 232 | 143 / 259 |
| `parallel` | .NET 10 | 19194 | 64.2 (112.2) | 0.379 / 3.772 | 2 227 | 97.1 % | 241 | 141 / 257 |
|  | .NET 11 | 22379 | 74.9 (137.5) | 0.216 / 1.150 | 2 296 | 96.8 % | 221 | 145 / 264 |
| `events` | .NET 10 | 2426 | 8.1 (66.3) | 0.540 / 1.954 | 2 188 | 92.4 % | 196 | 148 / 257 |
|  | .NET 11 | 2305 | 7.7 (72.1) | 0.424 / 2.960 | 2 225 | 92.2 % | 203 | 146 / 255 |
| `mixed` | .NET 10 load-events | 2545 | 8.6 (25.3) | 0.451 / 1.676 | 863 | 80.4 % | 238 | 173 / 300 |
|  | .NET 10 load-linear | 9964 | 33.5 (64.5) | 0.360 / 1.832 |  | | | |
|  | .NET 10 load-parallel | 7453 | 25.1 (48.3) | 0.217 / 1.092 |  | | | |
|  | .NET 11 load-events | 2792 | 9.4 (28.2) | 0.460 / 2.036 | 787 | 77.3 % | 243 | 166 / 303 |
|  | .NET 11 load-linear | 11040 | 37.1 (69.2) | 0.421 / 3.195 |  | | | |
|  | .NET 11 load-parallel | 8405 | 28.3 (53.7) | 0.251 / 1.621 |  | | | |

#### `timers-1m` (10 000 timers armed at 100 starts/s, due within one minute)

| runtime | armed | fired | failed / not fired | lag p50 / p99 / max (s) | starts answered `429` | CPU Fleans / total (%) |
|---|---:|---:|---|---|---:|---|
| r1 net10 | 9388 | 9388 | 0 / 0 | 0.126 / 0.572 / 2.416 | 5.5 % | 79 / 151 |
| r1 net11 | 9434 | 9434 | 0 / 0 | 0.145 / 0.791 / 2.315 | 5.0 % | 74 / 153 |
| r2 net10 | 9485 | 9485 | 0 / 0 | 0.136 / 0.477 / 1.563 | 4.4 % | 79 / 155 |
| r2 net11 | 9377 | 9377 | 0 / 0 | 0.088 / 0.515 / 2.312 | 5.6 % | 71 / 145 |

#### `signal-fanout` (10 000 parked at 100/s, one broadcast, linear-10 at 20/s before / during)

| runtime | parked / received | broadcast answered | delivery spread | linear-10 started before → during | linear-10 duration p99 before → during |
|---|---|---:|---:|---|---|
| r1 net10 | 9720 / 9720 | 878 ms | 21.658 s | 1203 → 1199 | 0.418 s → 2.197 s |
| r1 net11 | 9330 / 9330 | 874 ms | 22.123 s | 1205 → 1196 | 0.125 s → 2.948 s |
| r2 net10 | 9324 / 9324 | 1198 ms | 22.201 s | 1205 → 1197 | 0.357 s → 3.957 s |
| r2 net11 | 9433 / 9433 | 683 ms | 17.866 s | 1201 → 1200 | 0.101 s → 1.312 s |

#### `long-lived` (10 000 instances parked on a message, linear-10 with 20 VUs before / after)

| runtime | parked / still waiting | accepted linear-10 starts/s empty → loaded | drop | `429` empty / loaded | result |
|---|---|---|---:|---|---|
| r1 net10 | 8866 / 8866 | 151.8 → 149.5 | 1.5 % | 1206 / 0 | PASS |
| r1 net11 | 9688 / 9688 | 118.8 → 125.7 | -5.8 % | 6729 / 0 | PASS |
| r2 net10 | 9628 / 9628 | 140.9 → 143.1 | -1.6 % | 10261 / 74 | PASS |
| r2 net11 | 9741 / 9741 | 133.5 → 144.7 | -8.4 % | 4596 / 0 | PASS |

#### `mi-fanout` (one instance forks N branches, each waits for its own message)

| branches | .NET 10: start answered / all delivered (r1, r2) | .NET 11: start answered / all delivered (r1, r2) | journal batches / events (both) |
|---:|---|---|---|
| 100 | 4.3 / 1.3 s, 3.5 / 1.0 s | 3.9 / 1.2 s, 4.1 / 0.6 s | 200 / 1815 |
| 500 | 7.9 / 6.4 s, 6.9 / 5.3 s | 8.3 / 6.5 s, 5.5 / 4.7 s | 1000 / 9015 |
| 1000 | 9.1 / 26.9 s, 7.5 / 28.5 s | 8.9 / 20.2 s, 7.7 / 22.0 s | 2000 / 18015 |

#### Soak: `linear-10` at 45 starts/s, 5 min pre-warm + 30 s warm-up + **30 min** measured

| runtime | started | completed | failed / unfinished | completed /s | p50 / p95 / p99 / max (s) | CPU total (%) | Fleans processes (%) | peak MiB core / worker / api |
|---|---:|---:|---|---:|---|---:|---:|---|
| net10 | 81001 | 81001 | 0 / 0 | 45.0 | 0.055 / 0.191 / 0.293 / 0.993 | 269.7 | 152 | 229 / 269 / 148 |
| net11 | 80998 | 80998 | 0 / 0 | 45.0 | 0.049 / 0.162 / 0.260 / 0.946 | 252.9 | 135 | 271 / 252 / 143 |

Notes:

- **Soak** — the cleanest comparison in this report: one fixed, sustainable rate for 30 minutes.
  Every instance completed in both, .NET 11 with lower latency at every percentile and 11 % less CPU
  in the Fleans processes (Core 3 silos, API, Worker, gRPC workers); the databases did the same work.
  Peak Core-silo memory was higher on .NET 11 (271 against 229 MiB), the Worker's lower.
- **Classic scripts** are a heavy overload here (≈ 2 200 requests/s against a ~65 /s ceiling), so
  92–97 % of the starts are answered `429` by the admission limiter on both runtimes; what counts is
  the work that got through. .NET 11 completed more instances in `linear` (+13 %), `parallel` (+17 %)
  and `mixed` (+11 % over its three processes); `events` (start → wait → message → end) 5 % fewer.
  `events` saw no correlation miss on either runtime; 2 of 20 260 polls stalled on .NET 11, none
  of 18 525 on .NET 10. The p99s of overloaded runs swing either way between runs.
- **timers-1m**: every armed timer fired on both runtimes in both rounds; lag p99 0.57 / 0.48 s
  (.NET 10) against 0.79 / 0.52 s (.NET 11), p50 0.13 / 0.14 against 0.15 / 0.09 s — within the
  run-to-run spread, under the scenario's 2 s gate in all four runs.
- **signal-fanout**: every parked instance received the broadcast; linear-10 kept its start rate during
  the broadcast in all four runs (−0.1 to −0.8 %). Its p99 during the broadcast was 2.2 / 4.0 s on
  .NET 10 and 2.9 / 1.3 s on .NET 11.
- **long-lived**: every parked instance still waiting, PASS in all four runs. linear-10 here is a
  closed loop of 20 VUs far above the ceiling, so the start rate per window follows the admission
  limiter (thousands of `429` in some windows on both runtimes) — read it as pass / fail only.
- **mi-fanout**: the journal is byte-for-byte the same shape on both runtimes (200 / 1 000 / 2 000
  batches, 1 815 / 9 015 / 18 015 events), and delivering 1 000 branch messages — 1 000 turns of one
  grain, each rescanning its state — took 24 % less time on .NET 11 in both rounds.
- `fail` / `crit` log lines: 2 on the Core silos per run on both runtimes (EF's migration-history
  probe on a fresh database), none elsewhere.

### Memory

MiB per container (mean of the full rounds; idle = after `setup.js`, peak = highest 5 s sample of the
round, after = at the end of the round):

| service | idle .NET 10 / 11 | peak .NET 10 / 11 | after load .NET 10 / 11 |
|---|---|---|---|
| `fleans-core` | 156 / 161 | 361 / 384 | 338 / 356 |
| `fleans-api` | 110 / 115 | 188 / 187 | 174 / 179 |
| `fleans-worker` | 128 / 115 | 363 / 348 | 356 / 342 |
| `external-worker` | 17 / 17 | 59 / 60 | 58 / 59 |

### Startup

`docker compose up -d --wait` of the whole stack (17 containers, health checks every 10 s): .NET 10
36.3 / 37.2 s, .NET 11 37.3 / 36.4 s — the same.

## Correctness on .NET 11

From `src/Fleans` on the migration branch, .NET SDK 11.0.100:

| suite | result |
|---|---|
| `dotnet test --filter "TestCategory!=E2E"` (10 assemblies) | 2 111 passed, 0 failed, 235 skipped (Postgres rows, gated) |
| `FLEANS_PG_TESTS=1 dotnet test --filter "TestCategory=Postgres"` | 370 passed, 0 failed |
| `FLEANS_KAFKA_TESTS=1 … --filter "FullyQualifiedName~Kafka"` | 10 passed, 0 failed |
| fleans-plugins `FLEANS_PG_TESTS=1 dotnet test` | 41 + 164 passed, 0 failed |

| Playwright E2E, CI filter (`TestCategory=E2E`, no split-roles / auth) | 157 passed, 47 failed, 14 skipped |

All 47 E2E failures wait for bpmn-js to render (`.editor-page[data-editor-ready='true']` 41×,
`#bpmn-canvas` 6×). `Fleans.Web` loads bpmn-js from `unpkg.com`, which the test host's egress
proxy refused (403); two of the failing specs, run on the .NET 10 baseline on the same host, fail the
same way. Every spec that does not need bpmn-js passed. CI, with network access, is the run that
covers the editor.

## Caveats

- One 4-vCPU VM, k6 on the same host. The ladders use 1-minute windows; the 5 + 30 minute method of
  the roadmap was run once per runtime at 45 /s (the soak), not at every rate, and not on dedicated
  load generators. The scaled-down `timers-1m` / `signal-fanout` / `long-lived` (10 000 instances, not
  1 M / 100 000 / 10 M) do not answer those scenarios' capacity questions; they compare the runtimes. Differences under ~5 % are within the round-to-round spread; the CPU
  savings at 30–50 /s (10–17 %) and the p50 improvements are consistent across every round.
- The .NET 10 baseline is the current release line (10.0.15); .NET 11 is 11.0.0, the first GA
  build. Server GC, no `DOTNET_*` tuning in either.
- EF Core and Npgsql stay on 10.x in both builds, so the database client path is the same code.

## Reproducing

```bash
# .NET 10 baseline: a worktree of main, SDK 10 pinned
git worktree add ../fleans-net10 a50fcfe
# images: dotnet publish -c Release + FROM mcr.microsoft.com/dotnet/aspnet:10.0 (tests/load/build-images.sh with the TAG/base changed)
TAG=net11 bash tests/load/build-images.sh        # on the migration branch: aspnet:11.0

# one round (retags <label> → :loadtest, fresh stack, three scenarios)
LIN_RATES="30 45 60 75 90" ONE_RATES="50 100 150 200" DUR=1m LD_VUS=40 LD_DUR=3m scripts/run-round.sh net10 r1
scripts/run-ld.sh net11 ld1
python3 scripts/compare.py <results-dir>; python3 scripts/compare-ld.py
```

Directories: `r<N>-net1x/` hold the summaries of the full rounds (`linear10/`, `onetask/` ladders,
`long-diverse.summary.json`, idle / after-load `docker stats`, startup, runtime, error-line counts);
`ld<N>-net1x/` the isolated `long-diverse` rounds with the status of every failed start.
