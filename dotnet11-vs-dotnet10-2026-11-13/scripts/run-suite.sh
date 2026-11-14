#!/usr/bin/env bash
# run-suite.sh <scenario> <label>: one scenario of the rest of the suite on a fresh stack.
set -uo pipefail
SC="$1"; LABEL="$2"; OUT="/tmp/claude-0/work/results2/$SC-$LABEL"; mkdir -p "$OUT"
LOAD=/home/user/fleans/tests/load; K=/tmp/claude-0/work/k6
export FLEANS_CITUS_IMAGE=citusdata/citus:12.1 K6_TARGET_URL=http://localhost:80
cd $LOAD
for i in fleans-api fleans-worker fleans-external-worker; do docker tag "$i:$LABEL" "$i:loadtest"; done
docker compose down -v --remove-orphans >/dev/null 2>&1
docker compose up -d --wait > "$OUT/up.log" 2>&1 || echo "compose up failed"
docker compose exec -T nginx nginx -s reload >/dev/null 2>&1
EXPECTED_REPLICA_COUNT=2 bash verify-cluster.sh > "$OUT/verify.txt" 2>&1 || echo "verify failed"
docker exec fleans-load-fleans-core-1 dotnet --list-runtimes > "$OUT/runtime.txt" 2>&1
sql() { docker compose exec -T "${DB:-postgres}" psql -U postgres -d "${DBN:-fleans}" "$@"; }
( while true; do docker stats --no-stream --format "$(date +%s) {{.Name}} {{.CPUPerc}} {{.MemUsage}}"; sleep 3; done ) > "$OUT/stats-timeline.txt" 2>/dev/null &
sp=$!
echo "$(date +%s) start" > "$OUT/phases.txt"
case "$SC" in
  linear|parallel|events|mixed)
    (cd $K && k6 run -q scripts/setup.js > "$OUT/setup.k6.txt" 2>&1)
    echo "$(date +%s) load" >> "$OUT/phases.txt"
    (cd $K && k6 run --summary-export "$OUT/k6-summary.json" scripts/$SC.js > "$OUT/k6.txt" 2>&1)
    echo "$(date +%s) drain" >> "$OUT/phases.txt"
    sleep 60
    sql < scripts/throughput.sql > "$OUT/throughput.sql.txt" 2>&1 ;;
  timers)
    (cd $K && K6_TIMERS_COUNT=10000 K6_TIMERS_RATE=100 k6 run --summary-export "$OUT/k6-summary.json" scripts/timers-1m.js > "$OUT/k6.txt" 2>&1)
    echo "$(date +%s) armed" >> "$OUT/phases.txt"
    sleep 240
    sql < scripts/timers-1m-lag.sql > "$OUT/lag.sql.txt" 2>&1 ;;
  signal)
    (cd $K && K6_FANOUT_COUNT=10000 K6_FANOUT_RATE=100 K6_WINDOW_S=60 k6 run --summary-export "$OUT/k6-summary.json" scripts/signal-fanout.js > "$OUT/k6.txt" 2>&1)
    sleep 90
    sql < scripts/signal-fanout.sql > "$OUT/signal.sql.txt" 2>&1 ;;
  longlived)
    (cd $K && K6_PARK_COUNT=10000 K6_PARK_RATE=100 K6_WINDOW_S=60 K6_WARMUP_S=30 k6 run --summary-export "$OUT/k6-summary.json" scripts/long-lived.js > "$OUT/k6.txt" 2>&1)
    sleep 30
    sql < scripts/long-lived.sql > "$OUT/longlived.sql.txt" 2>&1 ;;
  mifanout)
    (cd $K && K6_MI_SIZES=100,500,1000 k6 run --summary-export "$OUT/k6-summary.json" scripts/mi-fanout.js > "$OUT/k6.txt" 2>&1)
    ids=$(grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" "$OUT/k6.txt" | sort -u | paste -sd, -)
    DB=citus-coord DBN=journal sql -v ids="'{$ids}'" < scripts/mi-fanout.sql > "$OUT/mi.sql.txt" 2>&1 ;;
  soak)
    (cd $K && k6 run -q scripts/setup.js > "$OUT/setup.k6.txt" 2>&1)
    OUT="$OUT/tp" RATES=45 PROCESS=load-linear-10 DURATION=30m WARMUP=30s PREWARM=5m WAIT_S=180 bash scripts/throughput-ceiling.sh > "$OUT/soak.log" 2>&1 ;;
esac
echo "$(date +%s) end" >> "$OUT/phases.txt"
kill $sp
for s in fleans-core fleans-api fleans-worker external-worker; do
  printf '%s %s\n' "$s" "$(docker compose logs --no-color $s 2>/dev/null | grep -cE '\b(fail|crit)\b|Unhandled exception')"; done > "$OUT/error-log-counts.txt"
docker compose logs --no-color fleans-core fleans-api fleans-worker external-worker 2>/dev/null | gzip -9 > "$OUT/silo-logs.txt.gz"
docker compose down -v >/dev/null 2>&1
echo "== done $SC $LABEL $(date +%T)"
