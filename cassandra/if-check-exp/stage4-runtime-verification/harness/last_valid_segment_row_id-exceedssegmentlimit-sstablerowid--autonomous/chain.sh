#!/usr/bin/env bash
# Run 1 cluster tier as one background job (after `cluster-run.py seed <slot>`). Usage: chain.sh <slot>
set -u
SLOT=${1:-2}; H=$(cd "$(dirname "$0")" && pwd); export OUT=$HOME/s4-b34-logs/b3/run1/cluster; mkdir -p $OUT
run() { python3 $H/cluster-run.py "$@" > $OUT/console-$1.log 2>&1; rm -rf $HOME/stage4-tmp/b34/c3/$1; }
run S1024 std 1024 $SLOT
run S256a std 256 $SLOT
run S16 std 16 $SLOT
run V1024 small 1024 $SLOT
run S256b std 256 $SLOT
echo "chain finished $(date -u +%FT%TZ)" > $OUT/chain-done.txt
