#!/usr/bin/env bash
# Run 1 cluster tier as one background job (amendment C2 matrix, 15 node starts). Usage: chain.sh <slot>
set -u
SLOT=${1:-3}; H=$(cd "$(dirname "$0")" && pwd); export OUT=$HOME/s4-b34-logs/b4/run1/cluster; mkdir -p $OUT
run() { python3 $H/cluster-run.py "$@" > $OUT/console-$1.log 2>&1; rm -rf $HOME/stage4-tmp/b34/c4/$1; }
rows() { echo $((40000000 / $1)); }
for L in 100 128 129 400; do run SH$L S heap $L $(rows $L) $SLOT; done
run SH129b S heap 129 $(rows 129) $SLOT
run SH129c S heap 129 $(rows 129) $SLOT
for L in 100 128 129 400; do run ZH$L Z heap $L $(rows $L) $SLOT; done
for L in 128 129; do run SO$L S off $L $(rows $L) $SLOT; run ZO$L Z off $L $(rows $L) $SLOT; done
run CTL1500 S heap 1500 100000 $SLOT guard
echo "chain finished $(date -u +%FT%TZ)" > $OUT/chain-done.txt
