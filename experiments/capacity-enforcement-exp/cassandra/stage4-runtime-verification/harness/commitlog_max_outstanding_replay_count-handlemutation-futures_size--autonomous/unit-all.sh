#!/usr/bin/env bash
# The whole unit tier (B2e.2-4 as amended): shakedown (C=2, N=2000, known answer peak_queue=3), then 3 x each C, then controls.
H=$(cd "$(dirname "$0")" && pwd); TREE=/mydata/jingsong-cass-s4/o100/c509-unit; OUT=/mydata/jingsong-cass-s4/o100/unit
P=-Dcassandra.commitlog_max_outstanding_replay_count
MODE=${1:-run}
if [ "$MODE" = shakedown ]; then bash $H/unit-run.sh $TREE $OUT/shakedown shake-C2 "$P=2 -Dreplay.n=2000"; exit; fi
for r in 1 2 3; do for C in 16 256 4096; do bash $H/unit-run.sh $TREE $OUT/run1 C$C-r$r "$P=$C"; done; done
bash $H/unit-run.sh $TREE $OUT/run1 ctlBytes "$P=4096 -Dreplay.bytes_cap=4096"
bash $H/unit-run.sh $TREE $OUT/run1 ctlFast "$P=4096 -Dreplay.consumer_nanos=0"
grep -h 'READING' $OUT/run1/run-*.log | sort -k4
