#!/usr/bin/env bash
export PATH=~/.dotnet:$PATH
cd /home/user/wt-pr2 && TAG=pr2 bash tests/load/build-images.sh || exit 1
cd /tmp/claude-0/work
for r in r1 r2; do for l in main pr2 pr; do bash onetask-round.sh $l $r; done; done
echo ALL_DONE
