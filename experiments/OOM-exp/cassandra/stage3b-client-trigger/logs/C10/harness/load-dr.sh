#!/usr/bin/env bash
# 3-b confirm C10, data-role variant LOAD lifetime (not a reading), from the T templates (same ring, roles, c10, vks).
# Admin: keyspace adm RF 2 + table + role dataatk with SELECT/MODIFY on adm.t. dataatk: ring over CQL -> RF 2
# sub-ranges at blockFor 2 -> T_hot; 1,000,000 rows into adm.t; token check; probes; traced attack queries at ONE,
# QUORUM, ALL. Flush/drain (harness); the templates are replaced (they keep c10/vks).
set -uo pipefail
ROOT=/mydata/s4/3b-C10; H=$ROOT/harness; R=$ROOT/runs/LOADDR; SHM=/dev/shm/3b-c10
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"; C="bash $H/ring-ctl.sh"; CL="bash $H/client.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$C start LOADDR A 8G || { log "LOADDR start failed"; exit 1; }
C10USER=cassandra C10PASS=cassandra $CL DR-a C10Load cql 127.0.0.1 $H/admin-dr.cql | tee "$R/admin-dr.txt"
export C10USER=dataatk C10PASS=dat-pw C10KS=adm
$CL DR-ring C10Load ring 127.0.0.1 > "$R/ring-cql.txt"; tail -1 "$R/ring-cql.txt"
python3 "$H/ringcalc-rf2.py" "$R/ring-cql.txt" "$R" | tee "$R/ringcalc.txt"
THOT=$(cat "$R/T_hot")
$CL DR-load C10Load load 127.0.0.1 1000000 "$THOT" 64 | grep -v '^loaded' | tee "$R/load.out"
$CL DR-tok C10Load tokcheck 127.0.0.1 | tail -1 | tee "$R/tokcheck.out"
$CL DR-probe C10Load cql 127.0.0.1 $H/probe-dataatk.cql > "$R/probes.txt" 2>&1; cat "$R/probes.txt" | cut -c1-220
for p in 7199 7299 7399; do $NT -p $p flush adm; done
for p in 7199 7299 7399; do echo "== $p"; $NT -p $p tablestats adm.t | grep -E 'SSTable count|Space used \(live\)|Number of partitions'; done | tee "$R/tablestats.txt"
for cl in ONE ONE QUORUM QUORUM ALL; do C10CL=$cl $CL DR-tr-$cl C10Load trace 127.0.0.1 test >> "$R/trace-$cl.txt" 2>&1; done
grep -h '^trace\|concurren\|Submitt\|Didn\|ERR\|Exception:' "$R"/trace-*.txt | cut -c1-200
$C stop LOADDR
for i in 1 2 3; do rm -rf "$SHM/template$i"; cp -a "$SHM/node$i" "$SHM/template$i"; rm -rf "$SHM/template$i"/saved_caches/*; done
du -sh "$SHM"/template* | tee -a "$R/tablestats.txt"
log "LOADDR done"
