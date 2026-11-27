#!/usr/bin/env bash
# onetask-round.sh <label> <round>: one-task ladder alone on a fresh stack.
set -uo pipefail
LABEL="$1"; ROUND="$2"; OUT="/tmp/claude-0/work/results3/$ROUND-$LABEL"; mkdir -p "$OUT"
cd /home/user/fleans/tests/load
export FLEANS_CITUS_IMAGE=citusdata/citus:12.1 K6_TARGET_URL=http://localhost:80
for i in fleans-api fleans-worker fleans-external-worker; do docker tag "$i:$LABEL" "$i:loadtest"; done
docker compose down -v --remove-orphans >/dev/null 2>&1
docker compose up -d --wait > "$OUT/up.log" 2>&1 || echo "compose up failed"
docker compose exec -T nginx nginx -s reload >/dev/null 2>&1
EXPECTED_REPLICA_COUNT=2 bash verify-cluster.sh > "$OUT/verify.txt" 2>&1 || echo "verify failed"
k6 run -q scripts/setup.js > "$OUT/setup.k6.txt" 2>&1
OUT="$OUT/onetask" RATES="50 100 150 200" PROCESS=load-one-task DURATION=1m WARMUP=20s PREWARM=30s bash scripts/throughput-ceiling.sh > "$OUT/onetask.log" 2>&1
for s in fleans-core fleans-api fleans-worker external-worker; do
  printf '%s %s\n' "$s" "$(docker compose logs --no-color $s 2>/dev/null | grep -cE '\b(fail|crit)\b|Unhandled exception')"; done > "$OUT/error-log-counts.txt"
docker compose logs --no-color fleans-core fleans-api fleans-worker external-worker 2>/dev/null | gzip -9 > "$OUT/silo-logs.txt.gz"
docker compose down -v >/dev/null 2>&1
echo "== done $ROUND $LABEL $(date +%T)"
