# `timers-1m` on a laptop — 2026-11-12

Issue #886: do Orleans reminders on PostgreSQL carry a large number of BPMN timers, or does Fleans
need the roadmap's sharded timer scheduler? Pass: timer lag p99 < 2 s and no timer lost.

**Verdict: fail on this hardware, and the cause is not the reminder store.** Past ~170 fires/s the
silos run out of capacity. Orleans then fires every due reminder at once with nothing limiting how
many run concurrently, and membership declares Core silos dead. Follow-up: #1066 (bound timer delivery).

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
docker compose exec -T postgres psql -U postgres -d fleans < scripts/timers-1m-lag.sql
```

## Results

| run | requested / armed | due minute fire rate | fired | timer lag p50 / p99 / max | cluster after the due minute |
|---|---:|---:|---:|---|---|
| [`10k/`](10k) | 10 000 / 9 923 | ~170/s | **9 923** | **0.030 / 0.148 / 0.352 s** — pass | healthy |
| [`60k/`](60k) | 60 000 / 59 464 | ~1 000/s | 20 132 four minutes after the due minute | 22.4 / 225 / 268 s (fired ones) | 1 of 3 Core silos declared dead |
| [`161k/`](161k) | 1 000 000 / 160 951 | ~2 700/s | 1 012, then stalled | 2.0 / 12.3 / 13.3 s (fired ones) | 2 of 3 Core silos and the Worker silo declared dead |

Lag is `CompletedAt − due time` from the read model; for the failed runs it covers only the timers that
fired. `armed` < requested in `10k`/`60k` is k6's `dropped_iterations` at the arrival-rate start plus
0.7 % 429s.

- **1 M could not be armed at 2 000/s.** Admission control (`AdaptiveConcurrencyLimiter`) answered
  84 % of starts with 429 and accepted ~320 starts/s (start p95 155 ms), so 160 951 timers were
  armed. Arming a full million at that rate takes ~55 minutes; it was not repeated, because 60 000 already
  fails in the due minute.
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

- Pending timers: reminders on Postgres hold them cheaply in memory and in the database. The 1 M
  pending count itself is not the problem.
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
