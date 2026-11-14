### Classic scenarios (`linear`, `parallel`, `events`, `mixed` — the scripts' own VU profiles)

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

### `timers-1m` (10 000 timers armed at 100 starts/s, due within one minute)

| runtime | armed | fired | failed / not fired | lag p50 / p99 / max (s) | starts answered `429` | CPU Fleans / total (%) |
|---|---:|---:|---|---|---:|---|
| r1 net10 | 9388 | 9388 | 0 / 0 | 0.126 / 0.572 / 2.416 | 5.5 % | 79 / 151 |
| r1 net11 | 9434 | 9434 | 0 / 0 | 0.145 / 0.791 / 2.315 | 5.0 % | 74 / 153 |
| r2 net10 | 9485 | 9485 | 0 / 0 | 0.136 / 0.477 / 1.563 | 4.4 % | 79 / 155 |
| r2 net11 | 9377 | 9377 | 0 / 0 | 0.088 / 0.515 / 2.312 | 5.6 % | 71 / 145 |

### `signal-fanout` (10 000 parked at 100/s, one broadcast, linear-10 at 20/s before / during)

| runtime | parked / received | broadcast answered | delivery spread | linear-10 started before → during | linear-10 duration p99 before → during |
|---|---|---:|---:|---|---|
| r1 net10 | 9720 / 9720 | 878 ms | 21.658 s | 1203 → 1199 | 0.418 s → 2.197 s |
| r1 net11 | 9330 / 9330 | 874 ms | 22.123 s | 1205 → 1196 | 0.125 s → 2.948 s |
| r2 net10 | 9324 / 9324 | 1198 ms | 22.201 s | 1205 → 1197 | 0.357 s → 3.957 s |
| r2 net11 | 9433 / 9433 | 683 ms | 17.866 s | 1201 → 1200 | 0.101 s → 1.312 s |

### `long-lived` (10 000 instances parked on a message, linear-10 with 20 VUs before / after)

| runtime | parked / still waiting | accepted linear-10 starts/s empty → loaded | drop | `429` empty / loaded | result |
|---|---|---|---:|---|---|
| r1 net10 | 8866 / 8866 | 151.8 → 149.5 | 1.5 % | 1206 / 0 | PASS |
| r1 net11 | 9688 / 9688 | 118.8 → 125.7 | -5.8 % | 6729 / 0 | PASS |
| r2 net10 | 9628 / 9628 | 140.9 → 143.1 | -1.6 % | 10261 / 74 | PASS |
| r2 net11 | 9741 / 9741 | 133.5 → 144.7 | -8.4 % | 4596 / 0 | PASS |

### `mi-fanout` (one instance forks N branches, each waits for its own message)

| branches | .NET 10: start answered / all delivered (r1, r2) | .NET 11: start answered / all delivered (r1, r2) | journal batches / events (both) |
|---:|---|---|---|
| 100 | 4.3 / 1.3 s, 3.5 / 1.0 s | 3.9 / 1.2 s, 4.1 / 0.6 s | 200 / 1815 |
| 500 | 7.9 / 6.4 s, 6.9 / 5.3 s | 8.3 / 6.5 s, 5.5 / 4.7 s | 1000 / 9015 |
| 1000 | 9.1 / 26.9 s, 7.5 / 28.5 s | 8.9 / 20.2 s, 7.7 / 22.0 s | 2000 / 18015 |

### Soak: `linear-10` at 45 starts/s, 5 min pre-warm + 30 s warm-up + **30 min** measured

| runtime | started | completed | failed / unfinished | completed /s | p50 / p95 / p99 / max (s) | CPU total (%) | Fleans processes (%) | peak MiB core / worker / api |
|---|---:|---:|---|---:|---|---:|---:|---|
| net10 | 81001 | 81001 | 0 / 0 | 45.0 | 0.055 / 0.191 / 0.293 / 0.993 | 269.7 | 152 | 229 / 269 / 148 |
| net11 | 80998 | 80998 | 0 / 0 | 45.0 | 0.049 / 0.162 / 0.260 / 0.946 | 252.9 | 135 | 271 / 252 / 143 |

### `fail` / `crit` log lines (Core / API / Worker / external worker)

- `timers`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `timers2`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `signal`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `signal2`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `longlived`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `longlived2`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `mifanout`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `mifanout2`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `linear`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `parallel`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `events`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `mixed`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
- `soak`: net10 2 / 0 / 0 / 0; net11 2 / 0 / 0 / 0
