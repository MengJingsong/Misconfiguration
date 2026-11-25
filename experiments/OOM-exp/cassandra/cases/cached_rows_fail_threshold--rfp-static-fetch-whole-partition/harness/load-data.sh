#!/usr/bin/env bash
# B29 templates (not readings), design §2.5 steps 3-4, adapted from B22's load-data.sh.
#   load-data.sh TA : LOAD lifetime: both up (8G each, loading only), schema, k=0..95 s='a' + 4,000 x 65,536 B rows and
#                     k=1000..1009 s='x' + 10 rows at CL ALL via node 1; flush both. F1: drain + stop node 1; via node 2 at CL ONE
#                     DELETE k then UPDATE s='x' for k=0..95; truncatehints on node 2; flush + compact node 2. Start node 1;
#                     compact node 1; checks (tablestats, getendpoints, CL ONE traced reads of s on both nodes); drain, stop;
#                     move the node dirs to template-TA-n1|n2.
#   load-data.sh TB : from a clone of TA, both up, the same DELETE + UPDATE for k=0..95 at CL ALL via node 1, flush both,
#                     drain, stop; template-TB-n1|n2.
set -uo pipefail
ROOT=/mydata/s4/b29; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
ts(){ for i in 1 2; do echo "== n$i"; $V nt $i tablestats b29.t | grep -E "SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum|Compacted partition mean"; done; }
if [ "$1" = TA ]; then
  L=LOAD-TA; R=$ROOT/runs/$L
  $V prep $L LOAD || exit 1
  $V start $L 1 8G auto && $V ready $L 1 || exit 1
  $V start $L 2 8G auto && $V ready $L 2 || exit 1
  $V ring $L || exit 1
  $C $L schema 127.0.0.1
  log "load test partitions"; $C $L load 127.0.0.1 0 96 4000 65536 a ALL
  log "load warm-up partitions"; $C $L load 127.0.0.1 1000 1010 10 65536 x ALL
  for i in 1 2; do $V nt $i flush b29; done; ts
  log "F1: node 1 down"; NODRAIN=0 $V stopn $L 1
  $C $L f1 127.0.0.2 0 96 ONE
  # amendment A1 (2026-11-24): timed-out F1 mutations are hinted after the write timeout and flushed to a hint file up to
  # 10 s later; truncate only after that (the first TA attempt truncated too early, see ta-fix.sh)
  sleep 30; $V nt 2 truncatehints; sleep 15; $V nt 2 truncatehints; echo "pending hints: $($V nt 2 listpendinghints 2>&1 | tr '\n' ' ')"; echo "n2 hints files: $(ls $ROOT/n2/hints | wc -l)"
  $V nt 2 flush b29; log "compact n2"; $V nt 2 compact b29 t; log "compact n2 done"
  mv $R/n1/logs $R/n1/logs.1st; mkdir -p $R/n1/logs
  # pc72 rerun (2026-11-24 evening): A1 made a hard check — truncate again right before node 1 restarts, and abort if node 1's
  # memtable holds any cell after the restart (a hint replay of F1 would undo the divergence)
  $V nt 2 truncatehints; echo "n2 hints files before n1 restart: $(ls $ROOT/n2/hints | wc -l)"
  $V start $L 1 8G auto && $V ready $L 1 || exit 1
  $V ring $L || exit 1
  sleep 20
  echo "n1 hints files: $(ls $ROOT/n1/hints | wc -l) n2: $(ls $ROOT/n2/hints | wc -l)"
  mc=$($V nt 1 tablestats b29.t | awk -F: '/Memtable cell count/{gsub(/ /,"",$2); print $2}')
  echo "n1 b29.t memtable cells after restart: $mc"
  [ "$mc" = 0 ] || { log "ABORT: n1 memtable not empty after restart (hint replay?)"; exit 3; }
  log "compact n1"; $V nt 1 compact b29 t; log "compact n1 done"; $V nt 1 compactionstats | head -3
  ts; $V nt 1 getendpoints b29 t 0
  $C $L stat 127.0.0.1 0 ONE trace; $C $L stat 127.0.0.2 0 ONE trace
  $V stop $L
  grep -c "OutOfMemoryError" $R/n1/logs/system.log $R/n2/logs/system.log
  for i in 1 2; do rm -rf $ROOT/template-TA-n$i; rm -rf $ROOT/n$i/saved_caches/*; mv $ROOT/n$i $ROOT/template-TA-n$i; done
  du -sh $ROOT/template-TA-n1 $ROOT/template-TA-n2
elif [ "$1" = TB ]; then
  L=LOAD-TB; R=$ROOT/runs/$L
  $V prep $L TA || exit 1
  $V start $L 1 8G auto && $V ready $L 1 || exit 1
  $V start $L 2 8G auto && $V ready $L 2 || exit 1
  $V ring $L || exit 1
  $C $L f1 127.0.0.1 0 96 ALL
  for i in 1 2; do $V nt $i flush b29; done; ts
  $C $L stat 127.0.0.1 0 ONE trace
  $V stop $L
  for i in 1 2; do rm -rf $ROOT/template-TB-n$i; rm -rf $ROOT/n$i/saved_caches/*; mv $ROOT/n$i $ROOT/template-TB-n$i; done
  du -sh $ROOT/template-TB-n1 $ROOT/template-TB-n2
fi
log "END load $1"
