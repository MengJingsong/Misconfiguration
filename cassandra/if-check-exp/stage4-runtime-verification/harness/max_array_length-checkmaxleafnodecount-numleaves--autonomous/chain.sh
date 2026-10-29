#!/usr/bin/env bash
# Run 1 cluster tier as one background job. Usage: chain.sh <slot>
set -u
SLOT=${1:-1}; H=$(cd "$(dirname "$0")" && pwd); export OUT=$HOME/s4-b34-logs/b2/run1/cluster; mkdir -p $OUT
run() { python3 $H/cluster-run.py "$@" > $OUT/console-$1.log 2>&1; rm -rf $HOME/stage4-tmp/b34/c2/$1; }
run R5 5000000 1024 $SLOT
run R20a 20000000 1024 $SLOT
run R40 40000000 1024 $SLOT
run R20b 20000000 1024 $SLOT
run C32 20000000 32 $SLOT
echo "chain finished $(date -u +%FT%TZ)" > $OUT/chain-done.txt
