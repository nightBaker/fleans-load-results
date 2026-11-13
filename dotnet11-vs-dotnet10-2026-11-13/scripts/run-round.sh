#!/usr/bin/env bash
# run-round.sh <label: net10|net11> <round-name>
# One full load round on a fresh stack: linear-10 + one-task throughput ladders, long-diverse constant load.
set -uo pipefail
LABEL="$1"; ROUND="$2"
OUT="/tmp/claude-0/work/results/$ROUND-$LABEL"; mkdir -p "$OUT"
cd /home/user/fleans/tests/load
export FLEANS_CITUS_IMAGE=citusdata/citus:12.1 K6_TARGET_URL=http://localhost:80
for i in fleans-api fleans-worker fleans-external-worker; do docker tag "$i:$LABEL" "$i:loadtest"; done
docker image inspect fleans-api:loadtest --format '{{.Id}}' > "$OUT/image-ids.txt"
docker compose down -v --remove-orphans >/dev/null 2>&1
t0=$(date +%s.%N)
docker compose up -d --wait > "$OUT/up.log" 2>&1 || { echo "compose up failed"; tail -20 "$OUT/up.log"; }
t1=$(date +%s.%N); python3 -c "print(f'compose_up_wait_s {$t1-$t0:.1f}')" > "$OUT/startup.txt"
docker compose exec -T nginx nginx -s reload
EXPECTED_REPLICA_COUNT=2 bash verify-cluster.sh > "$OUT/verify.txt" 2>&1 || echo "verify-cluster failed"
docker exec fleans-load-fleans-core-1 dotnet --list-runtimes > "$OUT/runtime.txt" 2>&1
k6 run -q scripts/setup.js > "$OUT/setup.k6.txt" 2>&1 || echo "setup.js failed"
sleep 5
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' > "$OUT/idle-stats.txt"
# memory sampler over the whole round
( while true; do docker stats --no-stream --format "$(date +%s) {{.Name}} {{.MemUsage}}"; sleep 5; done ) > "$OUT/mem-timeline.txt" 2>/dev/null &
mem_pid=$!
echo "== $ROUND $LABEL linear-10"; date
OUT="$OUT/linear10" RATES="${LIN_RATES}" PROCESS=load-linear-10 DURATION="${DUR:-1m}" WARMUP=20s PREWARM=60s bash scripts/throughput-ceiling.sh > "$OUT/linear10.log" 2>&1
echo "== $ROUND $LABEL one-task"; date
OUT="$OUT/onetask" RATES="${ONE_RATES}" PROCESS=load-one-task DURATION="${DUR:-1m}" WARMUP=20s PREWARM=30s bash scripts/throughput-ceiling.sh > "$OUT/onetask.log" 2>&1
echo "== $ROUND $LABEL long-diverse"; date
( cd /tmp/claude-0/work/k6 && K6_PROFILE=constant K6_VUS="${LD_VUS:-40}" K6_DURATION="${LD_DUR:-3m}" K6_SUMMARY_PATH="$OUT/long-diverse.summary.json" \
  k6 run scripts/long-diverse.js > "$OUT/long-diverse.k6.txt" 2>&1 )
kill $mem_pid
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' > "$OUT/after-stats.txt"
for s in fleans-core fleans-api fleans-worker external-worker; do
  printf '%s %s\n' "$s" "$(docker compose logs --no-color $s 2>/dev/null | grep -cE '\b(fail|crit)\b|Unhandled exception')"; done > "$OUT/error-log-counts.txt"
docker compose logs --no-color fleans-core fleans-api fleans-worker external-worker 2>/dev/null | gzip -9 > "$OUT/silo-logs.txt.gz"
docker compose down -v >/dev/null 2>&1
echo "== done $ROUND $LABEL"; date
