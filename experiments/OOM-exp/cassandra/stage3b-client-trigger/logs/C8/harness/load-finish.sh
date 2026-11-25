#!/usr/bin/env bash
# C8 3-b confirm (2026-11-24): the tail of load-life.sh, run by hand after the settle loop of the first LOAD driver was
# stopped (its grep expected "pending tasks: 0"; nodetool prints "pending tasks   0", fixed in load-life.sh since).
set -u
. $(dirname "$0")/common.sh
RID=$1; R=$W/runs/$RID; PID=$(dpid); exec >> $R/driver.txt 2>&1
log "load-finish.sh (settle loop stopped by hand; compactionstats: pending 0, completed 11, unchanged over the last samples)"
ls -l $T/data/data/c8/big-*/*-Data.db > $R/sstables-before-drain.txt 2>&1
NT tablestats c8.big > $R/tablestats-before-drain.txt 2>&1
log "count check (attacker): $(CQT=600 CQ -u attacker -p $APW --request-timeout=600 -e 'SELECT count(*) FROM c8.big' 2>&1 | tr '\n' ' ' | tr -s ' ')"
stop_monitors $R
NTT=300 NT drain; log "drain rc=$?"
stop_node $RID
ls -l $T/data/data/c8/big-*/*-Data.db > $R/sstables-after-drain.txt 2>&1
for f in $T/data/data/c8/big-*/*-Data.db; do echo "== $f"; $T/tools/bin/sstablemetadata $f 2>/dev/null | grep -E "Estimated partitions|totalRows|SSTable Level|Repaired at|Compressor|Minimum timestamp|Maximum timestamp" ; done > $R/sstablemetadata.txt 2>&1
rm -rf $TPL; mkdir -p $TPL; cp -a $T/data/. $TPL/; rm -rf $TPL/saved_caches
du -sh $TPL > $R/template-du.txt
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
log "LOAD done"
