#!/usr/bin/env bash
export PATH=~/.dotnet:$PATH LIN_RATES="30 45 60 75 90" ONE_RATES="50 100 150 200" DUR=1m LD_VUS=40 LD_DUR=3m
cd /tmp/claude-0/work
for r in r1 r2; do for l in main pr; do bash run-round.sh $l $r; done; done
echo ALL_DONE
