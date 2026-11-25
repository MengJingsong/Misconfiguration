#!/usr/bin/env bash
# B29 setup amendment A1 (2026-11-24 16:05 EST, before any reading): in load-data.sh TA, F1's DELETE/UPDATE mutations that timed
# out towards the just-stopped node 1 were hinted by node 2 AFTER `nodetool truncatehints` (hint file stamped 15:50:28, 3 s after
# the truncate) and replayed to node 1 at 15:57:03 when it restarted (node 1 memtable: 192 cells = 96 deletions + 96 statics).
# Fix applied by hand: load-data.sh stopped, node 1 killed with -9 (no flush), its commit log (2 segments, holding only the hint
# replay and system writes since the restart) deleted, node 2 hints checked empty and truncated again. This script then restarts
# node 1, checks its memtable is empty (no replayed F1 mutations), compacts node 1 and does the remaining TA checks of load-data.sh.
set -uo pipefail
ROOT=/mydata/s4/b29; H=$ROOT/harness; V="bash $H/ctl.sh"; C="bash $H/client.sh"; L=LOAD-TA; R=$ROOT/runs/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
ts(){ for i in 1 2; do echo "== n$i"; $V nt $i tablestats b29.t | grep -E "SSTable count|Space used \(live\)|Number of partitions|Compacted partition maximum|Memtable cell count"; done; }
mv $R/n1/logs $R/n1/logs.2nd; mkdir -p $R/n1/logs
echo "n2 hints files before restart: $(ls $ROOT/n2/hints | wc -l)"
$V start $L 1 8G auto && $V ready $L 1 || exit 1
$V ring $L || exit 1
sleep 20
echo "n1 memtable after restart: $($V nt 1 tablestats b29.t | grep -E 'Memtable cell count')"
echo "n2 hints files: $(ls $ROOT/n2/hints | wc -l); hint lines in n2 log since restart: $(grep -c 'Finished hinted handoff' $R/n2/logs/system.log)"
log "compact n1"; $V nt 1 compact b29 t; log "compact n1 done"; $V nt 1 compactionstats | head -3
ts; $V nt 1 getendpoints b29 t 0
for k in 0 95; do $C $L stat 127.0.0.1 $k ONE trace | grep -E "^stat|Read [0-9]+ live|Executing single-partition|reading data from|Merged data|Acquiring sstable"; $C $L stat 127.0.0.2 $k ONE trace | grep -E "^stat|reading data from|Executing single"; done
$V stop $L
grep -c "OutOfMemoryError" $R/n1/logs/system.log $R/n2/logs/system.log
for i in 1 2; do rm -rf $ROOT/template-TA-n$i; rm -rf $ROOT/n$i/saved_caches/*; mv $ROOT/n$i $ROOT/template-TA-n$i; done
du -sh $ROOT/template-TA-n1 $ROOT/template-TA-n2
log "END ta-fix"
