#!/usr/bin/env bash
# The whole unit tier of the case (B2e as amended U1-U5), one JVM per line. Output: $OUT/<label>.{out,log}; summary at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R=$H/unit-run.sh; export OUT=${OUT:-$HOME/stage4-logs/vlr/run1/unit}; mkdir -p "$OUT"
$R cap-len200 cap -Dprobe.sizes=1000,5000,50000,100000 -Dprobe.len=200 -Dprobe.extra=5000
$R cap-len2000 cap -Dprobe.sizes=100000 -Dprobe.len=2000 -Dprobe.extra=5000
$R cap-adds-lt-size cap -Dprobe.sizes=100000 -Dprobe.len=200 -Dprobe.extra=-99400
$R cap-50x cap -Dprobe.sizes=1000 -Dprobe.len=200 -Dprobe.mult=50
$R mt8 mt -Dprobe.sizes=1000 -Dprobe.per=200000
$R resolve-inproc resolve -Dprobe.props=unset,999,1000,1001,50000,50001,100000,100001,0,-1
for v in unset 999 1000 100000 100001; do
  if [ $v = unset ]; then $R resolve-D-unset resolve; else $R resolve-D-$v resolve -Dcassandra.virtual.logs.max.rows=$v; fi
done
echo "== unit tier done"; grep -h RESULT "$OUT"/*.out
