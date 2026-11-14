Rounds: r1, r2 (each round = fresh stack, net10 then net11)

### `linear-10` (10 script tasks, no waits)

Mean of the rounds. Latency = process duration from the read model (`CompletedAt − CreatedAt`), seconds; CPU = sum over all containers, % of one core.

| offered /s | .NET 10 done/s | .NET 11 done/s | .NET 10 p50 / p95 / p99 | .NET 11 p50 / p95 / p99 | Δ p99 | .NET 10 CPU | .NET 11 CPU | Δ CPU |
|---:|---:|---:|---|---|---:|---:|---:|---:|
| 30 | 30.0 | 30.0 | 0.043 / 0.105 / 0.166 | 0.038 / 0.075 / 0.106 | -35.6 % | 229 | 203 | -11.4 % |
| 45 | 45.0 | 45.0 | 0.071 / 0.223 / 0.304 | 0.045 / 0.154 / 0.244 | -19.7 % | 273 | 244 | -10.7 % |
| 60 | 59.8 | 60.0 | 0.168 / 1.189 / 1.896 | 0.090 / 0.780 / 1.683 | -11.3 % | 307 | 288 | -6.1 % |
| 75 | 75.0 | 75.0 | 0.354 / 0.863 / 1.097 | 0.217 / 0.692 / 0.930 | -15.2 % | 329 | 316 | -4.0 % |
| 90 | 90.0 | 90.0 | 3.011 / 5.927 / 7.043 | 2.605 / 4.728 / 5.835 | -17.1 % | 343 | 331 | -3.4 % |

Per round (p50 / p99 s, CPU %):

| offered /s | r1 net10 | r1 net11 | r2 net10 | r2 net11 |
|---:|---|---|---|---|
| 30 | 0.046 / 0.201, 240 | 0.040 / 0.120, 214 | 0.040 / 0.130, 218 | 0.035 / 0.093, 193 |
| 45 | 0.087 / 0.365, 282 | 0.054 / 0.265, 254 | 0.056 / 0.244, 264 | 0.037 / 0.224, 234 |
| 60 | 0.228 / 2.500, 313 | 0.116 / 1.088, 298 | 0.107 / 1.292, 301 | 0.065 / 2.277, 278 |
| 75 | 0.369 / 1.218, 329 | 0.314 / 1.292, 322 | 0.338 / 0.976, 329 | 0.121 / 0.568, 309 |
| 90 | 5.330 / 12.340, 347 | 4.930 / 9.931, 341 | 0.693 / 1.745, 339 | 0.280 / 1.739, 321 |

CPU per service (% of one core, mean of rounds):

- 30/s: external-worker 0 → 0; fleans-api 8 → 7; fleans-core 84 → 68; fleans-worker 34 → 30
- 45/s: external-worker 0 → 0; fleans-api 10 → 8; fleans-core 104 → 87; fleans-worker 37 → 35
- 60/s: external-worker 0 → 0; fleans-api 12 → 10; fleans-core 115 → 104; fleans-worker 37 → 38
- 75/s: external-worker 0 → 0; fleans-api 12 → 10; fleans-core 119 → 112; fleans-worker 37 → 37
- 90/s: external-worker 0 → 0; fleans-api 14 → 11; fleans-core 123 → 114; fleans-worker 36 → 36

### `one-task` (one external `e2e-probe` task on gRPC workers, 50 ms)

Mean of the rounds. Latency = process duration from the read model (`CompletedAt − CreatedAt`), seconds; CPU = sum over all containers, % of one core.

| offered /s | .NET 10 done/s | .NET 11 done/s | .NET 10 p50 / p95 / p99 | .NET 11 p50 / p95 / p99 | Δ p99 | .NET 10 CPU | .NET 11 CPU | Δ CPU |
|---:|---:|---:|---|---|---:|---:|---:|---:|
| 50 | 50.0 | 50.0 | 0.136 / 0.215 / 0.242 | 0.135 / 0.210 / 0.234 | -3.5 % | 216 | 192 | -11.2 % |
| 100 | 99.8 | 100.0 | 0.169 / 0.282 / 0.376 | 0.158 / 0.251 / 0.313 | -16.8 % | 301 | 281 | -6.7 % |
| 150 | 148.6 | 149.4 | 0.263 / 0.549 / 0.730 | 0.223 / 0.489 / 0.738 | +1.0 % | 326 | 319 | -2.2 % |
| 200 | 168.9 | 179.6 | 0.310 / 0.613 / 0.798 | 0.299 / 0.597 / 0.785 | -1.6 % | 332 | 326 | -1.6 % |

Per round (p50 / p99 s, CPU %):

| offered /s | r1 net10 | r1 net11 | r2 net10 | r2 net11 |
|---:|---|---|---|---|
| 50 | 0.135 / 0.246, 225 | 0.137 / 0.240, 201 | 0.137 / 0.239, 207 | 0.132 / 0.228, 183 |
| 100 | 0.175 / 0.380, 303 | 0.161 / 0.333, 286 | 0.163 / 0.372, 299 | 0.154 / 0.293, 276 |
| 150 | 0.292 / 0.877, 329 | 0.248 / 0.791, 323 | 0.234 / 0.583, 323 | 0.198 / 0.684, 314 |
| 200 | 0.353 / 0.908, 336 | 0.321 / 0.895, 333 | 0.268 / 0.688, 327 | 0.277 / 0.675, 319 |

CPU per service (% of one core, mean of rounds):

- 50/s: external-worker 6 → 5; fleans-api 17 → 14; fleans-core 80 → 66; fleans-worker 26 → 22
- 100/s: external-worker 11 → 8; fleans-api 25 → 22; fleans-core 112 → 103; fleans-worker 32 → 30
- 150/s: external-worker 13 → 9; fleans-api 28 → 26; fleans-core 114 → 112; fleans-worker 31 → 31
- 200/s: external-worker 14 → 10; fleans-api 29 → 27; fleans-core 116 → 113; fleans-worker 30 → 30

### `long-diverse` (≈45 nodes, 4 client interactions + external task), constant VUs

| metric | .NET 10 | .NET 11 | Δ |
|---|---:|---:|---:|
| completed iterations /s | 11.72 | 15.40 | +31.4 % |
| end-to-end med (ms) | 3164 | 3034 | -4.1 % |
| end-to-end p95 (ms) | 4444 | 4372 | -1.6 % |
| engine duration med (ms) | 2886 | 2784 | -3.5 % |
| engine duration p95 (ms) | 4070 | 4009 | -1.5 % |
| start request med (ms) | 57.2 | 39.8 | -30.4 % |
| start request p95 (ms) | 198.6 | 161.5 | -18.7 % |
| all HTTP med (ms) | 21.5 | 19.2 | -10.8 % |
| all HTTP p95 (ms) | 123.7 | 116.1 | -6.1 % |
| message accept p95 (ms) | 152.1 | 148.0 | -2.7 % |
| instances completed (rate) | 1.000 | 0.794 | -20.5 % |
| instances failed (rate) | 0.000 | 0.000 | — |
| checks passed (rate) | 0.9999 | 0.9499 | -5.0 % |
| HTTP failed (rate) | 0.0000 | 0.0176 | +54742.6 % |

### Memory (MiB per container, mean of rounds)

| service | idle .NET 10 | idle .NET 11 | peak .NET 10 | peak .NET 11 | after load .NET 10 | after load .NET 11 |
|---|---:|---:|---:|---:|---:|---:|
| fleans-core | 156 | 161 | 361 | 384 | 338 | 356 |
| fleans-api | 110 | 115 | 188 | 187 | 174 | 179 |
| fleans-worker | 128 | 115 | 363 | 348 | 356 | 342 |
| external-worker | 17 | 17 | 59 | 60 | 58 | 59 |

### Startup (`docker compose up -d --wait`, whole stack, s)

| | r1 | r2 |
|---|---:|---:|
| net10 | 36.3 | 37.2 |
| net11 | 37.3 | 36.4 |

### `fail`/`crit` log lines per service over the round

- r1 net10: fleans-core 2, fleans-api 0, fleans-worker 196, external-worker 0
- r1 net11: fleans-core 2, fleans-api 0, fleans-worker 245, external-worker 0
- r2 net10: fleans-core 2, fleans-api 0, fleans-worker 241, external-worker 0
- r2 net11: fleans-core 2, fleans-api 0, fleans-worker 215, external-worker 0
