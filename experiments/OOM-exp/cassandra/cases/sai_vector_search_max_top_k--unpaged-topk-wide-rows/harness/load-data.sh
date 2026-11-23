#!/usr/bin/env bash
# B21 lifetime LOAD (heap 8G, direct resolved; not a reading): schema, 4,000 rows x 122,880-char body at concurrency 4
# (CL ONE, <= 5 retries each), flush, major compaction, wait for no compaction task, check count, drain, stop; then the
# template every measured lifetime is cloned from.   load-data.sh LOAD
set -uo pipefail
ROOT=/mydata/s4/b21; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=${1:-LOAD}; R=$ROOT/runs/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L LOAD 8G && $V ready $L || { echo "INVALID start"; exit 1; }
bash $H/client.sh $L schema 127.0.0.1
log "load start"
bash $H/client.sh $L load 127.0.0.1 4000 122880 4 | tail -30
log "flush"; $NT flush b21; log "compact"; time $NT compact b21
for i in $(seq 1 120); do n=$($NT compactionstats 2>/dev/null | awk '/pending tasks/{print $3}'); [ "${n:-1}" = 0 ] && break; sleep 5; done
$NT compactionstats; $NT tablestats b21.docs | grep -E "SSTable count|Space used \(live\)|Number of partitions|Compression|Compacted partition (maximum|mean)"
bash $H/client.sh $L verify 127.0.0.1
grep -h -i "index\b.*built\|docs_emb" $R/logs/system.log | tail -5 | cut -c1-250
$V stop $L
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/b21/*/ | head -40
echo LOADDONE
