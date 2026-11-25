#!/usr/bin/env bash
# The whole unit tier (B2b/B2e): shakedown (N=10, m=200, every=50; known answer final size 10), then the B2b sweep.
H=$(cd "$(dirname "$0")" && pwd); OUT=/mydata/jingsong-cass-s4/o127/unit
P=-Dcassandra.parent_repair_status_cache_size
MODE=${1:-run}
if [ "$MODE" = shakedown ]; then bash $H/unit-run.sh $OUT/shakedown shake-N10 "$P=10 -Do127.m=200 -Do127.every=50"; exit; fi
bash $H/unit-run.sh $OUT/run1 N0      "$P=0 -Do127.m=50000 -Do127.len=1000"
bash $H/unit-run.sh $OUT/run1 N1      "$P=1 -Do127.m=50000 -Do127.len=1000"
bash $H/unit-run.sh $OUT/run1 N1000   "$P=1000 -Do127.m=50000 -Do127.len=1000"
bash $H/unit-run.sh $OUT/run1 N10000  "$P=10000 -Do127.m=50000 -Do127.len=1000"
bash $H/unit-run.sh $OUT/run1 Ndef    "-Do127.m=50000 -Do127.len=1000"
bash $H/unit-run.sh $OUT/run1 N1000-L100   "$P=1000 -Do127.m=50000 -Do127.len=100"
bash $H/unit-run.sh $OUT/run1 N1000-L10000 "$P=1000 -Do127.m=50000 -Do127.len=10000"
bash $H/unit-run.sh $OUT/run1 Nneg    "$P=-1 -Do127.m=50000 -Do127.len=1000"
grep -h 'READING.*FINAL\|READING.*cap=' $OUT/run1/run-*.log
