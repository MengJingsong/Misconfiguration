#!/usr/bin/env bash
# B21 3-b confirm lifetime LOAD (pc72, 2026-11-23; heap 8G, auth on; not a reading). Superuser: roles, admin schema
# (b21.docs + SAI index docs_emb, vic.kv), grants. Then the ATTACKER role (SELECT, MODIFY on b21.docs) loads the 4,000
# rows x 122,880-char body at concurrency 4 (stage 2's load), and the TENANT role writes its 1,000 keys. No nodetool
# flush/compact (deviation from stage 2: data placement left to the server; the template is taken after the drain of an
# ordinary stop). Then the template every measured lifetime is cloned from.   load-data.sh LOAD
set -uo pipefail
ROOT=/mydata/s4/3b-B21; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=${1:-LOAD}; R=$ROOT/runs/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L LOAD-AUTH 8G && $V ready $L || { echo "INVALID start"; exit 1; }
log "admin-setup (superuser)"; bash $H/client.sh $L cassandra B21Load admin-setup 127.0.0.1 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg"
log "load start (role attacker)"
bash $H/client.sh $L attacker B21Load load 127.0.0.1 4000 122880 4 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg" | tail -12
log "victim tenant setup (role tenant)"; bash $H/client.sh $L tenant B21Victim setup 127.0.0.1 1000 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg" | tail -3
$NT tablestats b21.docs | grep -E "SSTable count|Space used \(live\)|Memtable data size|Number of partitions|Memtable cell count"
log "verify (role attacker)"; bash $H/client.sh $L attacker B21Load verify 127.0.0.1 2>&1 | grep -v "^\s*at \|SchemaParser\|IllegalArg"
grep -h -i "index\b.*built\|docs_emb\|Enqueuing flush\|Completed flushing" $R/logs/system.log | tail -12 | cut -c1-250
$V stop $L
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/b21/*/ | head -40; ls $ROOT/template/data/b21/*/ | grep -c 'Data.db'
echo LOADDONE
