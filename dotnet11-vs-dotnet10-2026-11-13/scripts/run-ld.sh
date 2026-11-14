#!/usr/bin/env bash
# run-ld.sh <label> <round>: long-diverse alone on a fresh stack (30 s warm-up at 10 VUs, then 40 VUs × 4 min).
set -uo pipefail
LABEL="$1"; ROUND="$2"; OUT="/tmp/claude-0/work/results/$ROUND-$LABEL"; mkdir -p "$OUT"
cd /home/user/fleans/tests/load
export FLEANS_CITUS_IMAGE=citusdata/citus:12.1 K6_TARGET_URL=http://localhost:80
for i in fleans-api fleans-worker fleans-external-worker; do docker tag "$i:$LABEL" "$i:loadtest"; done
docker compose down -v --remove-orphans >/dev/null 2>&1
docker compose up -d --wait > "$OUT/up.log" 2>&1
docker compose exec -T nginx nginx -s reload >/dev/null 2>&1
EXPECTED_REPLICA_COUNT=2 bash verify-cluster.sh > "$OUT/verify.txt" 2>&1
k6 run -q scripts/setup.js > "$OUT/setup.k6.txt" 2>&1
cd /tmp/claude-0/work/k6
K6_PROFILE=constant K6_VUS=10 K6_DURATION=30s k6 run scripts/long-diverse.js > "$OUT/warmup.k6.txt" 2>&1
( while true; do docker stats --no-stream --format "$(date +%s) {{.Name}} {{.CPUPerc}} {{.MemUsage}}"; sleep 3; done ) > "$OUT/stats-timeline.txt" 2>/dev/null &
sp=$!
K6_PROFILE=constant K6_VUS=40 K6_DURATION=4m K6_SUMMARY_PATH="$OUT/long-diverse.summary.json" k6 run scripts/long-diverse.js > "$OUT/long-diverse.k6.txt" 2>&1
kill $sp
cd /home/user/fleans/tests/load
docker compose logs --no-color fleans-core fleans-api fleans-worker external-worker 2>/dev/null | gzip -9 > "$OUT/silo-logs.txt.gz"
docker compose down -v >/dev/null 2>&1
echo "== done $ROUND $LABEL"
