#!/usr/bin/env bash
# run.sh VARIANT COUNT RATE OUT — one timers-1m run on a fresh tests/load stack.
set -uo pipefail
VARIANT=$1 COUNT=$2 RATE=$3 OUT=$4
cd /home/user/fleans/tests/load
export FLEANS_CITUS_IMAGE=citusdata/citus:12.1 ${EXTRA_ENV:-}
docker tag fleans-api:$VARIANT fleans-api:loadtest; docker tag fleans-worker:$VARIANT fleans-worker:loadtest
docker compose down -v >/dev/null 2>&1
docker compose up -d --wait >$OUT.up.log 2>&1 || { echo "compose up failed"; tail -20 $OUT.up.log; }
docker compose exec -T nginx nginx -s reload
echo "== $(date -u +%T) arming $COUNT at $RATE/s ($VARIANT)"
docker run --rm --network host -v $PWD:/load -w /load/scripts -e K6_TARGET_URL=http://localhost:80 \
  -e K6_TIMERS_COUNT=$COUNT -e K6_TIMERS_RATE=$RATE grafana/k6:latest run --quiet timers-1m.js > $OUT.k6.log 2>&1
grep -E "timers-1m:|timers_armed|http_req_failed|checks" $OUT.k6.log | grep -v "^ *$" | head -12
end=$(( $(date +%s) + ${MAX_WAIT_S:-1500} ))
while [ $(date +%s) -lt $end ]; do
  sleep 30
  lag=$(docker compose exec -T postgres psql -U postgres -d fleans -At -F' ' < scripts/timers-1m-lag.sql 2>/dev/null)
  mem=$(docker compose exec -T postgres-ops psql -U postgres -d ops -At -F: -c "select count(*) filter (where status=3), count(*) filter (where status=6) from orleansmembershiptable" 2>/dev/null)
  restarts=$(docker ps -a --filter name=fleans-load-fleans --format '{{.Names}}' | xargs -r docker inspect -f '{{.RestartCount}}' | paste -sd+ | bc)
  stats=$(docker stats --no-stream --format '{{.Name}}={{.MemUsage}}' | grep fleans-core | sed 's/fleans-load-//;s/ \/.*//' | paste -sd' ')
  echo "$(date -u +%T) armed/fired/failed/not_fired/p50/p99/max=[$lag] silos active:dead=[$mem] restarts=$restarts $stats"
  set -- $lag
  [ -n "${4:-}" ] && [ "$1" -gt 0 ] && [ "$4" = "0" ] && break
done
docker compose logs fleans-core 2>/dev/null | grep -ciE "declared dead|DeclareDead|killed|OutOfMemory" | sed 's/^/core log dead\/oom lines: /'
