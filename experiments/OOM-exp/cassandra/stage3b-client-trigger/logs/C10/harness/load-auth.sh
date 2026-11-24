#!/usr/bin/env bash
# 3-b confirm C10 LOAD lifetime (not a reading). Auth on (PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager).
# Admin (superuser 'cassandra'): system_auth RF 3 + repair, roles, GRANTs, victim schema. Attacker (CREATE ON ALL
# KEYSPACES only): ring from system.local/peers over CQL -> T_hot, its own RF 1 keyspace + table, 1,000,000 rows, token
# check, traced attack queries. Victim: preload. Probes. Then flush/drain (harness), templates as stage 2.
set -uo pipefail
ROOT=/mydata/s4/3b-C10; H=$ROOT/harness; R=$ROOT/runs/LOAD; SHM=/dev/shm/3b-c10
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"; C="bash $H/ring-ctl.sh"; CL="bash $H/client.sh"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
$C start LOAD LOAD 8G || { log "LOAD start failed"; exit 1; }
for k in $(seq 1 60); do grep -h "Created default superuser role" $R/n*/logs/system.log && break; sleep 2; done
$NT -p 7199 status > "$R/status.txt" 2>&1; cat "$R/status.txt"
grep -h -E "^(authenticator|authorizer|role_manager|network_authorizer):" $R/n1/conf/cassandra.yaml | tee "$R/auth-settings.txt"
export C10USER=cassandra C10PASS=cassandra
$CL LOAD-a1 C10Load cql 127.0.0.1 $H/admin1.cql | tee "$R/admin.txt"
for p in 7199 7299 7399; do timeout 300 $NT -p $p repair -full system_auth > "$R/repair-$p.txt" 2>&1; tail -1 "$R/repair-$p.txt"; done
$CL LOAD-a2 C10Load cql 127.0.0.1 $H/admin2.cql | tee -a "$R/admin.txt"
log "attacker: ring over CQL"
export C10USER=attacker C10PASS=att-pw
$CL LOAD-ring C10Load ring 127.0.0.1 > "$R/ring-cql.txt"; tail -1 "$R/ring-cql.txt"
python3 "$H/ringcalc.py" "$R/ring-cql.txt" "$R" | tee "$R/ringcalc.txt"
THOT=$(cat "$R/T_hot")
$NT -p 7199 ring > "$R/ring.txt" 2>&1; mkdir -p "$R/xcheck"; python3 "$H/ringcalc.py" "$R/ring.txt" "$R/xcheck" | tee "$R/ringcalc-nodetool.txt"
cmp -s "$R/subranges.csv" "$R/xcheck/subranges.csv" && echo "ring xcheck: CQL ring == nodetool ring (subranges identical)" | tee -a "$R/ringcalc.txt" || echo "ring xcheck: DIFFERENT" | tee -a "$R/ringcalc.txt"
$CL LOAD-schema C10Load schema 127.0.0.1 | tee "$R/attacker-schema.txt"
$CL LOAD-load C10Load load 127.0.0.1 1000000 "$THOT" 64 | tee "$R/load.out"
$CL LOAD-tok C10Load tokcheck 127.0.0.1 | tee "$R/tokcheck.out"
export C10USER=victim C10PASS=vic-pw
$CL LOAD-vpre C10Victim preload 127.0.0.1 10000 | tee "$R/victim-preload.txt"
log "probes"
{ echo "== raw frames, no login"; python3 $H/preauth.py 127.0.0.1
  echo "== driver, no credentials"; C10USER= C10PASS= $CL LOAD-pn C10Load cql 127.0.0.1 $H/probe-noauth.cql
  echo "== nogrant"; C10USER=nogrant C10PASS=nog-pw $CL LOAD-png C10Load cql 127.0.0.1 $H/probe-nogrant.cql
  echo "== attacker"; C10USER=attacker C10PASS=att-pw $CL LOAD-pa C10Load cql 127.0.0.1 $H/probe-attacker.cql
  echo "== victim"; C10USER=victim C10PASS=vic-pw $CL LOAD-pv C10Load cql 127.0.0.1 $H/probe-victim.cql
  echo "== admin view"; C10USER=cassandra C10PASS=cassandra $CL LOAD-a3 C10Load cql 127.0.0.1 $H/admin3.cql
} > "$R/probes.txt" 2>&1
for p in 7199 7299 7399; do $NT -p $p flush c10; $NT -p $p flush vks; done
for p in 7199 7299 7399; do echo "== $p"; $NT -p $p tablestats c10.t | grep -E 'SSTable count|Space used \(live\)|Number of partitions'; done | tee "$R/tablestats.txt"
log "attacker: traced attack queries (fetch 5000 x2, fetch 20000 x1)"
export C10USER=attacker C10PASS=att-pw
for k in 1 2; do $CL LOAD-tr$k C10Load trace 127.0.0.1 test >> "$R/trace-test.txt" 2>&1; done
$CL LOAD-tr20k C10Load trace 127.0.0.1 test 20000 >> "$R/trace-test-fetch20000.txt" 2>&1
$CL LOAD-trM C10Load trace 127.0.0.1 M >> "$R/trace-M.txt" 2>&1
grep -h '^trace\|concurren\|Submitt\|Didn\|ERR\|Exception' "$R"/trace-*.txt | cut -c1-220
$C stop LOAD
for i in 1 2 3; do rm -rf "$SHM/template$i"; cp -a "$SHM/node$i" "$SHM/template$i"; rm -rf "$SHM/template$i"/saved_caches/*; done
du -sh "$SHM"/template* | tee -a "$R/tablestats.txt"
log "LOAD done"
