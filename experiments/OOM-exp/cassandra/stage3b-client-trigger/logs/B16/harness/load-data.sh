#!/usr/bin/env bash
# B16 3-b confirm lifetime LOAD (ms0611, 2026-11-23; heap 8G as stage 2's LOAD, auth on; not a reading). Superuser:
# roles, admin schema (b16.t, b16.m as stage 2, vic.kv for the tenant), grants. The ATTACKER role (SELECT, MODIFY on
# b16.t and b16.m) writes stage 2's data itself: t = 49,999 range deletes with 12,000-B bounds, m = 49,999 with 1,000-B
# bounds (UNLOGGED single-partition batches of 20, 4 in flight). The TENANT role writes its 1,000 keys. No nodetool
# flush/compact (stage 2 ran both as an operator convenience; here the server places the data; the template is taken
# after the drain of an ordinary stop). Then: attacker read-back of m and t (0 rows, 99,998 markers, client warnings),
# claim checks (authcheck, pre-auth frames), tablestats; stop; template.     load-data.sh [LOAD]
set -uo pipefail
ROOT=/mydata/s4/3b-B16; H=$ROOT/harness; V="bash $H/victim-ctl.sh"; NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
L=${1:-LOAD}; R=$ROOT/runs/$L
C="bash $H/client.sh"
F(){ grep -v "^\s*at \|SchemaParser\|IllegalArg"; }
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$V start $L LOAD-AUTH 8G && $V ready $L || { echo "INVALID start"; exit 1; }
log "admin-setup (superuser cassandra)"; $C $L-admin cassandra B16Load admin-setup 127.0.0.1 2>&1 | F | tee $R/admin-setup.txt
log "load t (role attacker)"; $C $L-t attacker B16Load load 127.0.0.1 t 49999 12000 20 4 2>&1 | F | tail -3 | tee $R/load-t.txt
$V read $L after-t | cut -c1-220
log "load m (role attacker)"; $C $L-m attacker B16Load load 127.0.0.1 m 49999 1000 20 4 2>&1 | F | tail -3 | tee $R/load-m.txt
log "tenant setup (role tenant)"; $C $L-ten tenant B16Victim setup 127.0.0.1 1000 2>&1 | F | tail -3 | tee $R/tenant-setup.txt
[ "$($V alive $L)" = ALIVE ] || { log "VICTIM DEAD during load"; $V oom $L; exit 1; }
timeout 120 $NT tablestats b16 vic | grep -E 'Table:|SSTable count|Space used \(live\)|Compacted partition maximum bytes|Number of partitions|Memtable data size|Memtable cell count' | tee $R/tablestats-preread.txt
grep -h "Enqueuing flush\|Completed flushing\|Flushing largest" $R/logs/system.log $R/logs/debug.log 2>/dev/null | grep -i "b16\|t)\|m)" | cut -c1-250 | tail -12 | tee $R/flush-lines.txt
log "read-back (role attacker)"; for tb in m t; do $C $L-one attacker B16Load one 127.0.0.1 $tb 2>&1 | F | tee -a $R/readback.txt; done
$V tblm $L readback
grep -h "tombstone cells" $R/logs/system.log | cut -c1-300 | tail -4 | tee -a $R/readback.txt
log "authcheck"; $C $L-ac none B16Load authcheck 127.0.0.1 2>&1 | F | tee $R/authcheck.txt
log "preauth frames"; python3 $H/preauth.py 127.0.0.1 2>&1 | tee $R/preauth.txt
grep -v 'Node configuration' $R/logs/system.log | grep -h -i "guardrail\|clustering\|65535\|too large" | cut -c1-300 | tail -6 > $R/guardrail-excerpt.txt
$V read $L end | cut -c1-220
$V stop $L
grep -c "OutOfMemoryError" $R/logs/system.log
rm -rf $ROOT/template; cp -a $ROOT/node $ROOT/template; rm -rf $ROOT/template/saved_caches/*
du -sh $ROOT/template | tee -a $R/readback.txt; ls -la $ROOT/template/data/b16/*/ | tee $R/sstables.ls | grep -E 'Data.db|Index.db'; df -h /mydata | tail -1
log "LOAD end"
