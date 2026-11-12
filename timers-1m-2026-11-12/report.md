# `timers-1m` on a laptop — 2026-11-12

Issue #886: do Orleans reminders on PostgreSQL carry a large number of BPMN timers, or does Fleans
need the roadmap's sharded timer scheduler? Pass: timer lag p99 < 2 s and no timer lost.

**Verdict: fail on this hardware.** The full million was armed at 300/s: 829 491 timers were pending,
all silos stayed alive, and the reminders database stayed under one core. When they fell due, **none
fired**: the Core silos sat at their 1 GB limit in back-to-back GC pauses (thread pool stalled up to
42 s). Below the fire capacity, 10 000 per minute passes with lag p99 0.15 s; 60 000 already fails.
Follow-up, as the issue asks: #1066 (sharded timer scheduler / bounded timer delivery).

## Setup

- Fleans `main` @ `9789859c` — Orleans 10.4 (`ReminderLoadingWindow` at its 10-minute default),
  reminders on their own Postgres (`postgres-ops`) with the `(ServiceId, GrainHash)` index, bucket
  projector (#1064).
- `tests/load/docker-compose.yml` unchanged: 2 API, 3 Core (1 GB each), 1 Worker (512 MB), Citus
  journal (coordinator + 2 workers), read-model primary + replica, Kafka, `postgres-ops` for
  membership and reminders. Images from `tests/load/build-images.sh`.
- Apple M1 Pro (10 cores, 16 GB), Docker 29.9 VM with 10 CPU / 11.7 GB; k6 0.54.
- Every run on a fresh stack (`docker compose down -v && up -d --wait`).

```bash
K6_TARGET_URL=http://localhost:80 K6_TIMERS_COUNT=10000   K6_TIMERS_RATE=200 k6 run scripts/timers-1m.js   # 10k/
K6_TARGET_URL=http://localhost:80 K6_TIMERS_COUNT=60000   K6_TIMERS_RATE=300 k6 run scripts/timers-1m.js   # 60k/
K6_TARGET_URL=http://localhost:80                                             k6 run scripts/timers-1m.js   # 161k/ (1 M requested)
K6_TARGET_URL=http://localhost:80                         K6_TIMERS_RATE=300 k6 run scripts/timers-1m.js   # 1m/  (1 M requested)
docker compose exec -T postgres psql -U postgres -d fleans < scripts/timers-1m-lag.sql
```

## Results

| run | requested / armed | due minute fire rate | fired | timer lag p50 / p99 / max | cluster after the due minute |
|---|---:|---:|---:|---|---|
| [`10k/`](10k) | 10 000 / 9 923 | ~170/s | **9 923** | **0.030 / 0.148 / 0.352 s** — pass | healthy |
| [`60k/`](60k) | 60 000 / 59 464 | ~1 000/s | 20 132 four minutes after the due minute | 22.4 / 225 / 268 s (fired ones) | 1 of 3 Core silos declared dead |
| [`161k/`](161k) | 1 000 000 / 160 951 (2 000/s) | ~2 700/s | 1 012, then stalled | 2.0 / 12.3 / 13.3 s (fired ones) | 2 of 3 Core silos and the Worker silo declared dead |
| [`1m/`](1m) | 1 000 000 / **829 486** (300/s, 56 min) | ~13 800/s | **0** eight minutes after the due minute | — | all silos alive, at the 1 GB limit, GC-bound |

Lag is `CompletedAt − due time` from the read model; for the failed runs it covers only the timers that
fired. `armed` < requested in `10k`/`60k` is k6's `dropped_iterations` at the arrival-rate start plus
0.7 % 429s.

- **1 M at 300/s ([`1m/`](1m)).** 1 000 107 starts over 56 minutes; 17 % were answered 429, so
  829 491 instances parked on a timer and 829 493 reminders sat in `postgres-ops`. Arming itself
  was healthy: Core silos ~100 % CPU on average, reminders-Postgres 30 % (peak 141 %), no silo
  suspected. During the due minute the reminders database was idle (0–2 % CPU) and the Core and Worker
  silos ran flat at ~112 % CPU at their memory limit, logging 47 runtime stalls (GC pauses of 3–8 s,
  thread-pool stalls up to 42 s, [`1m/gc-stalls.txt`](1m/gc-stalls.txt)). Nothing fired, nothing
  failed, and nobody was declared dead: with every reminder inside `ReminderLoadingWindow` and each
  fire needing an activation, ~275 000 reminders per silo did not fit next to the instance activations in 1 GB.
- **1 M could not be armed at 2 000/s.** Admission control (`AdaptiveConcurrencyLimiter`) answered
  84 % of starts with 429 and accepted ~320 starts/s (start p95 155 ms), so 160 951 timers were
  armed; the `1m/` run repeats it at 300/s.
- **The reminder path is not the limit.** Reminders-Postgres (`postgres-ops`) averaged 14 % (161k)
  and 93 % (60k) of one core during the due minute, with peaks of 106 % and 221 %. The
  `ix_reminderstable_serviceid_grainhash` index served the range reads (`idx_scan` 450 after the 161k run).
- **A pending reminder is cheap; an activation is not.** gcdump of core-1 at the end of arming the
  60k run ([`60k/gcdump-core1-end-of-arming.txt.gz`](60k)), 302 MB heap: 18 479 pending reminders
  (`LocalReminderService` state machines) ≈ 4.7 MB, ~250 B each; 35 028 grain activations
  (15 111 `WorkflowInstance` with state and stream handles, the rest `TimerCallbackGrain`) take most
  of the rest.
- **The due minute is where it breaks.** Each fire reactivates a `WorkflowInstance` (journal snapshot
  read), appends, projects and completes — ~10 ms of laptop CPU per fire
  ([`target-arch-2026-10-24`](../target-arch-2026-10-24/report.md#timers-and-waiting-instances)),
  so this stack fires ~170–340 timers/s. Above that, every due reminder still fires at once: the Core
  silos stayed at their 1 GB limit at 150–200 % CPU, timed out on grain placement and directory calls,
  missed membership probes and were declared dead (`OrleansMembershipTable` status 6), and their reminder
  ranges stopped firing. No container was OOM-killed. Error counts by event:
  [`161k/core-warnings-by-event.txt`](161k/core-warnings-by-event.txt).

Compared with `target-arch-2026-10-24` (pre-merge branch, before Orleans 10.4 and the GrainHash index),
10 000 per minute passes again with the same lag, and 60 000 per minute still fails — now with a silo
declared dead instead of only memory saturation.

## What it means for 1.0

- Pending timers: 829 000 pending timers sat in Postgres and in the silos without trouble while
  they were far from due. They stop being cheap once they are all inside `ReminderLoadingWindow` and fall due together.
- Timers falling due together: the fire rate is bounded by engine capacity, like any other start or
  transition. 1 M in one minute is 16 700 fires/s ≈ 170 laptop cores for that minute (see the
  2026-10-24 estimate). What must change is how a burst above capacity behaves. Today it takes silos down;
  it should turn into lag instead. That is #1066: bound concurrent timer deliveries per silo, or the
  roadmap's scheduler shards, which pace delivery by design.

## Files

- `*/lag.txt` — `scripts/timers-1m-lag.sql` output.
- `*/k6-summary.txt`, `161k/k6-summary.json` — k6 end-of-run summary.
- `*/docker-stats.log.gz` — `docker stats` every 5 s (CPU %, memory per container).
- `161k/core-warnings-by-event.txt` — Core silo warnings and errors, counted by logger and event id.
- `60k/gcdump-core1-end-of-arming.txt.gz` — `dotnet-gcdump report` of core-1, 185 s into arming.
