#!/usr/bin/env bash
# The whole cluster tier (B3b): N=100, N=10000, default; one fresh node per value. Optional "shakedown" = N=100, M=1000.
H=$(cd "$(dirname "$0")" && pwd); P=-Dcassandra.parent_repair_status_cache_size
if [ "${1:-run}" = shakedown ]; then bash $H/cluster-run.sh shake-N100-M1000 "$P=100" 1000 500; exit; fi
bash $H/cluster-run.sh N100 "$P=100"
bash $H/cluster-run.sh N10000 "$P=10000"
bash $H/cluster-run.sh Ndef ""
grep -h 'SAMPLE\|COUNT\|PROBE\|DRIVE done' /mydata/jingsong-cass-s4/o127/cluster/{N100,N10000,Ndef}/session.txt
