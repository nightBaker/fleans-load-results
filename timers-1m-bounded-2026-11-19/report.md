# timers-1m with bounded timer delivery — 2026-11-19

Follow-up to the 2026-11-12 laptop run, where 60 000 timers due within one minute got Core silos
declared dead ([#1066](https://github.com/nightBaker/fleans/issues/1066)). This run measures the
per-silo bound on concurrent timer deliveries, `Fleans:Timers:DeliveryConcurrency`: a reminder tick
that finds every slot of its silo busy is skipped, and the timer's reminder ticks again a minute later.

## Setup

- **Hardware:** 4-vCPU Intel Xeon @ 2.10 GHz, 15 GB RAM, Ubuntu 24.04 VM, Docker 29.10 directly on
  the VM (no Docker Desktop VM layer).
- **Stack:** `tests/load/docker-compose.yml` unchanged except the journal image: Citus from
  `citusdata/citus:12.1` (`FLEANS_CITUS_IMAGE`), not built from source. 3 Core silos (1 GB each),
  1 Worker silo, 2 Api processes, Citus coordinator + 2 workers, Postgres primary + replica,
  reminders and membership on `postgres-ops`, Kafka.
- **Builds:** `main` @ `253c06c` (unbounded). Bounded: the #1066 branch, `ca72020` for the 32 / 64 /
  128 rows (the value set with `FLEANS_TIMER_DELIVERY_CONCURRENCY`), `0ab8319` (default 64) for the
  10 000 row. Images built with [`build.sh`](build.sh) (as `tests/load/build-images.sh`, without Citus).
- **Procedure** ([`run.sh`](run.sh)): fresh stack (`docker compose down -v && up -d --wait`), then
  `k6 run scripts/timers-1m.js` with `K6_TIMERS_COUNT` and `K6_TIMERS_RATE`, then every ~35 s
  `scripts/timers-1m-lag.sql`, the membership table (`status` 3 = active, 6 = dead), container
  restart counts and Core silo memory, until every armed timer fired. Timelines in [`runs/`](runs).

## Results

| Run | Build, `DeliveryConcurrency` | Requested / armed (rate) | All fired, after the due minute | Lag p50 / p99 / max | Core silos |
|---|---|---|---:|---|---|
| r3 | `main` (unbounded) | 60 000 / 59 099 (120/s) | ~15 min | 430 / 900 / 907 s | 8 declared dead, 8 restarts (OOM at 1 GB) |
| r4 | bounded, 32 | 60 000 / 57 230 (120/s) | ~10.5 min | 240 / 540 / 600 s | healthy, ≤ 540 MB |
| r6 | bounded, **64** | 60 000 / 58 802 (120/s) | ~6.5 min | 120 / 300 / 360 s | healthy, ≤ 660 MB |
| r5 | bounded, 128 | 60 000 / 58 670 (120/s) | ~6 min | 61 / 360 / 360 s | healthy, ≤ 720 MB |
| r7 | bounded, **64** (default) | 10 000 / 9 471 (100/s) | < 30 s | 0.10 / 0.47 / 2.3 s | healthy |
| r1 | bounded, 32 | 3 000 / 2 503 (100/s) | < 20 s | 0.04 / 0.52 / 1.7 s | healthy |
| r2 | `main` (unbounded) | 20 000 / 19 283 (100/s) | ~1 min | 1.2 / 19.8 / 27.7 s | healthy |

Armed < requested: admission control answered the rest of the starts with 429.

## Findings

- **The burst no longer takes the cluster down.** Unbounded, the 60 000 burst filled the Core silos
  to their 1 GB limit within about three minutes; they were OOM-killed and declared dead 8 times, and the
  last timer fired ~15 minutes after its due minute. Bounded, no silo was declared dead or restarted
  at any setting, and Core memory stayed under ~720 MB.
- **Lag grows with the overload, in whole minutes.** A deferred tick waits for its reminder's next
  tick, so bounded lag is a staircase of 60 s steps. Even so the bounded runs drained faster than
  the unbounded one, which spent its time restarting silos.
- **64 is the default.** 32 → 64 cut the drain from ~10.5 to ~6.5 minutes; 64 → 128 shaved another
  half minute for ~60 MB more per silo.
- **Below capacity nothing changes.** 10 000 due within one minute (~160/s) fired with lag p99 0.47 s.
  The pass line is p99 < 2 s.
- **This VM is faster than the laptop stack.** Unbounded, it survived 20 000 due within one minute
  (r2), where the laptop's limit was around 10 000. The failure point moved up; it did not go away (r3).
- **Fixture caveat.** `timers-1m.js` gives every instance of one key the same `timeDate`, so one
  second's timers fall due at the same instant. The slots fill at once and the rest of that second
  defers a minute. Real timers are spread over each second, so they should drain faster (not measured).

Not measured here: the full million (the 2026-11-12 run's 829 486 armed stalled the silos before
any fired) and reminders-Postgres CPU.
