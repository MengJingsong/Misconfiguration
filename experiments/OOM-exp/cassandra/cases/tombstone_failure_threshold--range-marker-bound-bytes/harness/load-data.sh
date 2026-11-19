#!/usr/bin/env bash
# B16 LOAD lifetime (heap 8G, arm LOAD = shipped defaults; not a reading): schema; t (49,999 ranges, 12,000-B bounds)
# and m (49,999 ranges, 1,000-B bounds); flush, compact, tablestats, read-back of both tables; drain; stop; template.
set -uo pipefail
ROOT=/mydata/s4/b16-w4; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; R=$ROOT/runs/LOAD
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start LOAD LOAD 8G || exit 1
$V ready LOAD || { log "LOAD not ready"; $V stop LOAD; exit 1; }
bash $H/load.sh LOAD-schema schema 127.0.0.1
log "load t"; bash $H/load.sh LOAD-t load 127.0.0.1 t 49999 12000 20 4 | tail -3; $V read LOAD after-t | cut -c1-220
log "load m"; bash $H/load.sh LOAD-m load 127.0.0.1 m 49999 1000 20 4 | tail -3
[ "$($V alive LOAD)" = ALIVE ] || { log "VICTIM DEAD during load"; $V oom LOAD; exit 1; }
log flush; timeout 900 $NT flush b16; log compact; timeout 1800 $NT compact b16; log "compact done"
timeout 120 $NT tablestats b16 | grep -E 'Table:|SSTable count|Space used \(live\)|Compacted partition maximum bytes|Number of partitions' | tee $R/tablestats.txt
ls -la $ROOT/node/data/b16/*/ | tee $R/sstables.ls
for tb in m t; do bash $H/load.sh LOAD-one one 127.0.0.1 $tb | tee -a $R/readback.txt; done
$V tblm LOAD readback
grep -h "tombstone cells" $R/logs/system.log | cut -c1-300 | tail -4 | tee -a $R/readback.txt
$V read LOAD end | cut -c1-220
$V stop LOAD
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template | tee -a $R/readback.txt; df -h /mydata | tail -1
log "LOAD end"
