#!/usr/bin/env bash
# B17 3-b confirm lifetime LOAD (pc75, 2026-11-23; heap 8G / direct 4096M as stage 2's LOAD, auth on; not a reading).
# Superuser (default cassandra role): roles, admin schema (b17.t, vic.kv), grants (B17Load admin-setup). Then the ATTACKER
# role (SELECT, MODIFY on b17.t) loads 16 partitions x 1,024 rows x 262,144 random bytes at 16 concurrent inserts (stage 2's
# load), and the TENANT role writes its 1,000 keys. No nodetool flush / compact (stage 2 ran both as data preparation, an
# operator step): placement is left to the server's own memtable flushes and background compaction, which the script
# only waits for (compactionstats pending = 0, bounded 30 min) before the ordinary drain-on-stop. Then the template.
set -uo pipefail
ROOT=/mydata/s4/3b-B17; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=${1:-LOAD}; R=$ROOT/runs/$L; D=$ROOT/out/$L
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
F="^\s*at \|SchemaParser\|IllegalArg"
$V start $L LOAD-AUTH 8G 4096M && $V ready $L || { echo "INVALID start"; exit 1; }
sleep 10
log "admin-setup (superuser)"; bash $H/client.sh $L cassandra B17Load admin-setup 127.0.0.1 2>&1 | grep -v "$F"
log "load start (role attacker)"
time bash $H/client.sh $L attacker B17Load load 127.0.0.1 16 1024 262144 16 2>&1 | grep -v "$F" | tail -15
log "load end"
log "victim tenant setup (role tenant)"; bash $H/client.sh $L tenant B17Victim setup 127.0.0.1 1000 2>&1 | grep -v "$F" | tail -3
log "verify (role attacker)"; bash $H/client.sh $L attacker B17Load verify 127.0.0.1 2>&1 | grep -v "$F"
for i in $(seq 1 180); do
  p=$($NT compactionstats 2>/dev/null | awk '/pending tasks/{print $3}'); [ "${p:-1}" = 0 ] && break; sleep 10
done
log "compaction pending=$p after $((i*10)) s"
$NT tablestats b17.t | grep -E "SSTable count|Space used \(live\)|Compacted partition (maximum|mean)|Number of partitions|Compression|Memtable data size"
grep -h "Enqueuing flush\|Completed flushing\|Compacted (" $R/logs/debug.log $R/logs/system.log 2>/dev/null | grep -i "b17\|\.t\b\|t-" | wc -l | sed 's/^/flush+compaction log lines for b17: /'
grep -h "Compacted (" $R/logs/system.log $R/logs/debug.log 2>/dev/null | grep -i "b17" | tail -5 | cut -c1-300
$V stop $L
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf /dev/shm/3b-B17-commitlog
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template; ls -la $ROOT/template/data/b17/*/ | grep Data.db
rm -rf $D; mkdir -p $D; cp $R/{run.meta,yaml.diff} $D/; cp $ROOT/runs/$L.out $D/load.out 2>/dev/null
echo LOADDONE
