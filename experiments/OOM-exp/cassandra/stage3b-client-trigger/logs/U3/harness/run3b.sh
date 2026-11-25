#!/usr/bin/env bash
# U3 stage 3-b confirm run (2026-11-24, ms0625; second session: node-events.txt OOM timestamps, auth-failure grep, post-run analysis). From stage 2's run.sh/golden.sh with auth on (PasswordAuthenticator +
# CassandraAuthorizer), a non-superuser attacker role and a victim role (R13's victim.py: own keyspace, 10 ops/s).
# usage: bash run3b.sh <run-id> <mode> [c=16] [window=180]
#   LOAD : fresh node, 2 GiB heap. Superuser: roles + u3.s1m/u3.n1m + victim.kv + GRANTs (admin.cql). Probes (privileges,
#          pre-auth frames). ATTACKER grows u3.s1m: 8 sets x 10^6 by 80 appends of 100,000 ints. One single read check.
#          Then harness mechanics as stage 2 (superuser/nodetool): flush, compact s1m, tablestats, drain -> $R/golden/data.
#   T    : golden start; victim 30 s; attacker's 16 readers on u3.s1m (stage 2's T arm), window 180 s.
#   NF   : golden start; victim; ATTACKER appends 8 x 10^6 into u3.n1m in this lifetime (no flush/compact/restart), then
#          16 readers on u3.n1m (claim: flush + compact not needed).
#   SO   : golden start; victim; role selonly (SELECT on u3.s1m only) runs the 16 readers on the attacker-grown u3.s1m.
set -uo pipefail
RUNID=$1; MODE=$2; CC=${3:-16}; WIN=${4:-180}; HEAP=2G; GUARD=16G
source /mydata/s4/3b-U3/harness/lib3b.sh
RUN=$R/runs/$RUNID; N=$RUN/node; L=$RUN/logs
[ -e "$RUN" ] && { echo "run dir exists: $RUN"; exit 2; }
mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,conf} "$L/clients"
preflight
APW=attacker-pw-3b; VPW=victim-pw-3b; SPW=selonly-pw-3b; NPW=nogrant-pw-3b
case $MODE in T|NF) RU=attacker; RP=$APW; TB=s1m ;; SO) RU=selonly; RP=$SPW; TB=s1m ;; LOAD) ;; *) die "mode $MODE" ;; esac
[ "$MODE" = NF ] && TB=n1m
note "RUN $RUNID mode=$MODE heap=$HEAP guard=$GUARD table=${TB:-s1m} mode=set c=$CC window=$WIN role=${RU:-} start_epoch=$(date +%s)"
{ hostname; uname -mr; nproc; free -b; df -B1 /mydata | tail -1; java -version 2>&1; python3 --version; } > "$L/env.txt" 2>&1
( cd "$H" && sha256sum *.sh *.py *.cql ) > "$L/harness-sha256.txt"
cp -R "$C/conf/." "$N/conf/"; write_yaml "$N"
[ "$MODE" != LOAD ] && cp -a "$R/golden/data/." "$N/data/"
ulimit -n 100000
client() { local u=$1 p=$2; shift 2; log "+ [$u] u3client3b.py $*"; local r; r=$(U3_USER=$u U3_PW=$p python3 -I "$H/u3client3b.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
finish() {
  [ -n "${RDPID:-}" ] && { kill -- -"$RDPID" 2>/dev/null; pkill -P "$RDPID" 2>/dev/null; }
  pkill -f "u3client3b.py readers" 2>/dev/null
  [ -n "${VP:-}" ] && { touch "$L/VSTOP"; sleep 2; kill "$VP" 2>/dev/null; }
  stop_node
  for f in "$L"/*.hprof; do [ -e "$f" ] && note "HPROF $f $(stat -c %s "$f") birth=$(stat -c %W "$f") mtime=$(stat -c %Y "$f")"; done
  rm -rf "$N/data" "$N/commitlog" "$N/hints" "$N/saved_caches" "$N/cdc_raw"
  kill "${EVPID:-}" 2>/dev/null
  note "END end_epoch=$(date +%s) daemons_left=$(my_daemons | wc -l) clients_left=$(pgrep -fc 'u3client3b.py|victim.py')"
  if [ "$MODE" != LOAD ]; then
    python3 -I "$H/analyze.py" "$L" > "$L/analysis.txt" 2>&1; python3 -I "$H/a2.py" "$L/analysis.txt" >> "$L/analysis.txt" 2>&1
    python3 -I "$H/victim_summary.py" "$L" > "$L/victim-summary.txt" 2>&1
  fi
}
trap finish EXIT
start_node "$N" "$HEAP" "$GUARD" "3bu3-$RUNID"
wait_su
if [ "$MODE" = LOAD ]; then
  { echo "== superuser (cassandra) admin.cql"; cat "$H/admin.cql"; CQ -u cassandra -p cassandra -f "$H/admin.cql" && echo "== setup OK"
    echo "== perms"; CQ -u cassandra -p cassandra -f "$H/perms.cql"
    echo "== guardrail/threshold settings (system_views.settings, superuser view)"
    CQ -u cassandra -p cassandra -e "SELECT name, value FROM system_views.settings" | grep -E 'items_per_collection|collection_size|read_thresholds|local_read_size|coordinator_read_size|partition_size|max_mutation_size|concurrent_reads |authenticator|authorizer'
  } > "$L/auth-setup.txt" 2>&1
  grep -q "== setup OK" "$L/auth-setup.txt" || die "auth setup failed"
  { echo "== attacker negative probes (expect Unauthorized)"
    for q in "SELECT * FROM victim.kv LIMIT 1" "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}" \
             "CREATE TABLE u3.x (k int PRIMARY KEY, v set<int>)" "ALTER TABLE u3.s1m ADD w int" "GRANT SELECT ON TABLE u3.s1m TO nogrant"; do
      echo "-- attacker: $q"; CQ -u attacker -p $APW -e "$q" 2>&1 | tail -1; done
    echo "== attacker positive probe"; echo "-- attacker: SELECT k FROM u3.s1m LIMIT 1"; CQ -u attacker -p $APW -e "SELECT k FROM u3.s1m LIMIT 1" 2>&1 | tail -3
    echo "== nogrant probes"; for q in "SELECT v FROM u3.s1m WHERE k = 0" "UPDATE u3.s1m SET v = v + {1} WHERE k = 0"; do echo "-- nogrant: $q"; CQ -u nogrant -p $NPW -e "$q" 2>&1 | tail -1; done
    echo "== selonly probes"; echo "-- selonly: UPDATE u3.s1m SET v = v + {1} WHERE k = 0"; CQ -u selonly -p $SPW -e "UPDATE u3.s1m SET v = v + {1} WHERE k = 0" 2>&1 | tail -1
    echo "== unauthenticated cqlsh"; CQ -e "SELECT v FROM u3.s1m WHERE k = 0" 2>&1 | tail -1
    echo "== wrong password"; CQ -u attacker -p wrong -e "SELECT v FROM u3.s1m WHERE k = 0" 2>&1 | tail -1
    echo "== pre-auth frames (preauth.py)"; python3 -I "$H/preauth.py" 127.0.0.1
    echo "== pre-auth append (preauth-append.py)"; python3 -I "$H/preauth-append.py" 127.0.0.1
  } > "$L/probes.txt" 2>&1
  log "probes done"
  NT tablestats u3 > "$L/tablestats-before.txt" 2>&1
  T0=$(date +%s)
  client attacker $APW loadset s1m 1000000 100000 8
  note "LOAD attacker loadset s1m took $(( $(date +%s) - T0 )) s"
  NT tablestats u3.s1m > "$L/tablestats-after-load.txt" 2>&1
  U3_USER=attacker U3_PW=$APW python3 -I "$H/u3client3b.py" readers s1m set 1 15 "$L/clients/check" > "$L/check.out" 2>&1
  note "CHECK single reader (attacker) $(awk '{print $5, $6}' $L/clients/check.* | sort | uniq -c | tr '\n' ';')"
  CQ -u attacker -p $APW -e "SELECT k, writetime(v) FROM u3.s1m" > "$L/attacker-select-k.txt" 2>&1
  log "+ flush/compact (harness mechanics, superuser via nodetool)"; NT flush u3 >> "$L/commands.log" 2>&1
  (cd "$C" && timeout 1200 bin/nodetool compact u3 s1m) >> "$L/commands.log" 2>&1
  NT tablestats u3 > "$L/tablestats.txt" 2>&1
  note "SIZES $(grep -E 'Table: |SSTable count:|Space used \(live\):' "$L/tablestats.txt" | sed 's/^[[:space:]]*//' | tr '\n' ';')"
  (cd "$C" && timeout 300 bin/nodetool drain) >> "$L/commands.log" 2>&1
  grep -E 'WARN|ERROR' "$L/system.log" | cut -c1-300 > "$L/error-warn.txt"
  stop_node
  mkdir -p "$R/golden/data"; cp -a "$N/data/." "$R/golden/data/"; rm -rf "$R/golden/data/saved_caches"
  note "GOLDEN data du=$(du -sb "$R/golden/data" | cut -f1) commitlog_files=$(ls "$N/commitlog" | wc -l)"
  exit 0
fi
CQ -u cassandra -p cassandra -f "$H/perms.cql" > "$L/perms.txt" 2>&1
start_tpstats
setsid nohup python3 -I "$H/victim.py" --user victim --pw $VPW --rate 10 --out "$L/victim.txt" --stop "$L/VSTOP" --src 127.0.0.1 < /dev/null > "$L/victim.err" 2>&1 &
VP=$!
sleep 30
if [ "$MODE" = NF ]; then
  drv "load start (attacker appends into u3.n1m, no flush) at_ms $(date +%s%3N)"
  T0=$(date +%s)
  client attacker $APW loadset n1m 1000000 100000 8
  note "LOAD attacker loadset n1m took $(( $(date +%s) - T0 )) s"
  drv "load end at_ms $(date +%s%3N)"
  NT tablestats u3.n1m > "$L/tablestats-n1m.txt" 2>&1
  note "N1M $(grep -E 'SSTable count:|Memtable cell count|Memtable data size|Space used \(live\):' "$L/tablestats-n1m.txt" | sed 's/^[[:space:]]*//' | tr '\n' ';')"
  sleep 5
fi
note "CLIENTS start epoch=$(date +%s.%N) table=$TB mode=set c=$CC role=$RU"
drv "attack start role=$RU table=$TB c=$CC at_ms $(date +%s%3N)"
( U3_USER=$RU U3_PW=$RP setsid python3 -I "$H/u3client3b.py" readers "$TB" set "$CC" "$WIN" "$L/clients/r" > "$L/readers.out" 2>&1 ) &
sleep 0.5
RDPID=$(pgrep -f "u3client3b.py readers $TB set $CC $WIN $L/clients/r" | head -1)
T0=$(date +%s); OUTCOME=survived; OOMSEEN=""
while :; do
  sleep 1
  if [ -z "$OOMSEEN" ] && grep -q -E 'OutOfMemoryError|Dumping heap' "$L/node-events.txt" 2>/dev/null; then OOMSEEN=1; note "OOME seen (node-events) at t=$(( $(date +%s) - T0 ))s: $(head -1 "$L/node-events.txt" | cut -c1-160)"; fi
  if ! kill -0 "$DPID" 2>/dev/null; then OUTCOME=died; note "DAEMON DIED at epoch=$(date +%s.%N) t=$(( $(date +%s) - T0 ))s"; drv "daemon gone while attack running at_ms $(date +%s%3N)"; break; fi
  [ $(( $(date +%s) - T0 )) -ge "$WIN" ] && { drv "attack clients ended; daemon alive (hold end) at_ms $(date +%s%3N)"; break; }
done
for p in $(pgrep -f "u3client3b.py readers $TB set $CC $WIN $L/clients/r"); do kill "$p" 2>/dev/null; done
sleep 1
for p in $(pgrep -f "u3client3b.py readers $TB set $CC $WIN $L/clients/r"); do kill -9 "$p" 2>/dev/null; done
note "CLIENTS stopped epoch=$(date +%s.%N)"
if [ $OUTCOME = survived ]; then
  if grep -q 'Dumping heap to' "$L/node.out" && ! grep -q 'Heap dump file created' "$L/node.out"; then
    log "dump in progress at window end: wait <= 600 s"; for i in $(seq 1 600); do grep -q 'Heap dump file created' "$L/node.out" && break; kill -0 "$DPID" 2>/dev/null || break; sleep 1; done
  fi
  if [ -n "$OOMSEEN" ] || grep -q -E 'OutOfMemoryError|Dumping heap' "$L/node-events.txt"; then
    log "OOME thrown, daemon alive at window end: wait <= 150 s for the shipped kill -9"
    for i in $(seq 1 150); do kill -0 "$DPID" 2>/dev/null || { note "DAEMON DIED (after window) at epoch=$(date +%s.%N)"; break; }; sleep 1; done
  else
    timeout 120 jcmd "$DPID" GC.class_histogram > "$L/histo-end.txt" 2>&1
    note "HISTO end | $(grep -E '^Total' "$L/histo-end.txt") | cells $(grep -E 'org\.apache\.cassandra\.db\.rows\.ArrayCell$' "$L/histo-end.txt" | awk '{print $2, $3}')"
  fi
fi
log "victim after-phase 30 s"; sleep 30; touch "$L/VSTOP"; sleep 2; kill "$VP" 2>/dev/null; VP=""
note "OOMKILL $(tail -1 "$L/memory.txt")"
note "STDOUT-OOM $(grep -c '^java.lang.OutOfMemoryError: ' "$L/node.out") | $(grep -v CompileCommand "$L/node.out" | grep -m4 -E 'OutOfMemoryError|Dumping heap|Heap dump file created|kill -9' | tr '\n' ' ' | cut -c1-400)"
grep -n -E '^(ERROR|WARN)' "$L/system.log" | cut -c1-300 > "$L/error-warn.txt"
note "SYSLOG ERROR=$(grep -c ':ERROR' "$L/error-warn.txt") WARN=$(grep -c ':WARN' "$L/error-warn.txt") first_error=$(grep -m1 ':ERROR' "$L/error-warn.txt" | cut -c1-250)"
note "AUTHZ-LOG $(grep -c -i -E 'roles cache|permissions cache|UnavailableException.*system_auth|Unable to perform authentication|AuthenticationException|UnauthorizedException' "$L/system.log")"
note "AUTHZ-DEBUG $(grep -h -c -E 'Failed to authorize|Unable to perform authorization|Unable to perform authentication|Roles.java|CassandraAuthorizer.java|PermissionsCache|RolesCache' "$L/system.log" "$L/debug.log" 2>/dev/null | tr '\n' ' ')"
grep -h -E 'Failed to authorize|Unable to perform authorization|Unable to perform authentication|Roles.java:|CassandraAuthorizer.java:|PermissionsCacheRefresh|RolesCacheRefresh' "$L/debug.log" 2>/dev/null | cut -c1-300 > "$L/auth-failures.txt"
note "OUTCOME-RAW $OUTCOME"
