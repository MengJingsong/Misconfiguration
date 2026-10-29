#!/usr/bin/env bash
# Run 1 cluster tier as one background job (slot 0 = 127.0.0.1, JMX 7199). Usage: chain.sh <slot>
set -u
SLOT=${1:-0}; H=$(cd "$(dirname "$0")" && pwd); export OUT=$HOME/s4-b34-logs/b1/run1/cluster; mkdir -p $OUT
run() { python3 $H/cluster-run.py "$@" > $OUT/console-$1.log 2>&1; rm -rf $HOME/stage4-tmp/b34/c1/$1; }
run B2 B 2000000 1024 $SLOT
run B8a B 8000000 1024 $SLOT
run A2 A 2000000 1024 $SLOT
run A8 A 8000000 1024 $SLOT
run C2 C 2000000 1024 $SLOT
run C8 C 8000000 1024 $SLOT
run B8b B 8000000 1024 $SLOT
run B8c B 8000000 1024 $SLOT
run B8ctl16 B 8000000 16 $SLOT
echo "chain finished $(date -u +%FT%TZ)" > $OUT/chain-done.txt
