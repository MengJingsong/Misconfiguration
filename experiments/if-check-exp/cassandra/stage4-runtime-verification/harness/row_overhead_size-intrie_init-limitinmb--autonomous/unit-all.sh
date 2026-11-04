#!/usr/bin/env bash
# The whole unit tier (B2e as amended), one JVM per line. Output: $OUT/<label>.{out,log}; summary at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R=$H/unit-run.sh; export OUT=${OUT:-$HOME/stage4-logs/ros/run1/unit}; mkdir -p "$OUT"
# valid values: real keys until the flip, then 10 percent more
for k in 1 16 64 512; do $R off-$k OFF_HEAP $k true; done
$R off-default OFF_HEAP default true
$R off-2047 OFF_HEAP 2047 true
$R on-16 ON_HEAP 16 true
$R on-64 ON_HEAP 64 true
# invalid values: class initialisation must fail with the AssertionError (threshold-only runs)
for k in 0 2048 -5 -1 abc; do $R bad-$k OFF_HEAP $k false -Dprobe.skiplist=true; done
# controls: cassandra.trie_size_limit_mb has no effect; the same -D sizes the skip-list memtable's row overhead (bytes)
$R ctl-triesize64 OFF_HEAP default false -Dcassandra.trie_size_limit_mb=64
$R ctl-skiplist-unset OFF_HEAP default false -Dprobe.skiplist=true
$R ctl-skiplist-64 OFF_HEAP 64 false -Dprobe.skiplist=true
echo "== unit tier done"; grep -h -E "THRESHOLD|FLIP|END10|CLINIT_FAIL|SKIPLIST" "$OUT"/*.out
