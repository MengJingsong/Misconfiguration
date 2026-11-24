#!/usr/bin/env bash
# R14 stage 3-b confirm (ms0604, 2026-11-23): one clean lifetime of the verified test arm T-CK-8192M (one prepared
# SELECT * FROM u5.ck WHERE pk = ? AND c1 IN ? AND c2 IN ?, 160 x 1,600,000 bound ints, 12.8 MB) with
# PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager, sent by a role holding only SELECT on u5.ck.
# Adapted from the case harness run-arm.sh (same start options, scope, instruments, throw/dump/exit detection and
# lifetime end) and C2's 3-b run-3b.sh (role/grant setup by the superuser via cqlsh, privilege and pre-auth checks,
# victim-tenant client victim.py). Fresh node directory per lifetime; schema + the one row made by the superuser.
#   run-3b.sh <label> [heap=8192M] [direct=15872M] [k1=160] [k2=1600000] [W=600] [G=600]
set -uo pipefail
L=$1 HEAP=${2:-8192M} DIRECT=${3:-15872M} K1=${4:-160} K2=${5:-1600000} WIN=${6:-600} GRACE=${7:-600}
ROOT=/mydata/s4/3b-R14; H=$ROOT/h; BASE=/mydata/s4/cassandra-base; TREE=$ROOT/tree; R=$ROOT/runs/$L; IP=127.0.0.1
ATK_U=atk ATK_P=atk-pw-3b VIC_U=tenant VIC_P=tenant-pw-3b NG_U=nogrant NG_P=nogrant-pw-3b
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }
su_cql(){ timeout 60 "$TREE/bin/cqlsh" $IP -u cassandra -p cassandra -e "$1"; }
as_cql(){ timeout 60 "$TREE/bin/cqlsh" $IP -u "$1" -p "$2" -e "$3"; }
UCG=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service
log "BEGIN 3B $L heap=$HEAP direct=$DIRECT k1=$K1 k2=$K2 N=$(( K1 * K2 )) W=${WIN}s G=${GRACE}s"
if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; log "END $L REFUSED"; exit 1; fi
HM=$(mib "$HEAP")
FREE=$(( $(df --output=avail -k /mydata | tail -1) / 1024 ))
log "free /mydata ${FREE} MiB"
# deviation from run-arm.sh (heap + 20 GiB): this node's /mydata is 39 GiB; the 8 GiB dump is ~14 GiB
if [ $FREE -lt $(( HM + 10240 )) ]; then log "REFUSE: free ${FREE} MiB < heap + 10 GiB"; log "END $L REFUSED-disk"; exit 1; fi
[ -d "$TREE" ] || { cp -a "$BASE" "$TREE"; log "copied $BASE -> $TREE"; }
rm -rf "$ROOT/node" "$R"; mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw} "$R/logs"
cp -r "$BASE/conf" "$R/conf"; Y=$R/conf/cassandra.yaml
sed -i \
  -e "s|^# data_file_directories:|data_file_directories:|" \
  -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
  -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
  -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
  -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
  -e "s|^role_manager: CassandraRoleManager|role_manager: CassandraRoleManager|" "$Y"
diff "$BASE/conf/cassandra.yaml" "$Y" > "$R/yaml.diff"
EX="-Xlog:gc*,safepoint:file=$R/gc.log:time,uptime,level,tags:filecount=10,filesize=50m"
MM=$(( HM + 6144 ))
cat > "$R/run.meta" <<EOF
label=$L heap=$HEAP direct=$DIRECT k1=$K1 k2=$K2 N=$(( K1 * K2 )) W_s=$WIN G_s=$GRACE scopeMemoryMax=${MM}M tree=$TREE
start_utc=$(date -u '+%FT%TZ') node=$(hostname -s) arch=$(uname -m)
EOF
sha256sum "$TREE"/build/apache-cassandra-5.0.9-SNAPSHOT.jar >> "$R/run.meta"
cat "$UCG/memory.events" > "$R/parent.memory.events.before" 2>/dev/null
: > "$R/stdout.log"
( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
  CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EX" \
  setsid nohup systemd-run --user --scope --unit="r14-3b-$L-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
    "$TREE/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
( setsid nohup bash -c "tail -n +1 -F '$R/stdout.log' 2>/dev/null | python3 -u '$H/ts.py' '$R/stdout.ts'" < /dev/null > /dev/null 2>&1 & echo $! > "$R/ts.pid" )
P=""; for i in $(seq 1 30); do sleep 1; P=$(pgrep -f "Dcassandra.logdir=$R/logs " | head -1); [ -n "$P" ] && break; done
stopts(){ kill -- -"$(cat "$R/ts.pid")" 2>/dev/null; }
[ -z "$P" ] && { log "no java pid"; stopts; log "END $L INVALID-nopid"; exit 1; }
echo "$P" > "$R/cass.pid"; CGP=$(sed -n 's/^0:://p' /proc/"$P"/cgroup); echo "$CGP" > "$R/cgroup.path"
alive(){ kill -0 "$P" 2>/dev/null; }
log "started pid $P cgroup $CGP"
ok=0; for i in $(seq 1 90); do
  grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null && { ok=1; break; }
  alive || break; sleep 2; done
if [ $ok = 0 ]; then log "not ready in 180 s"; kill -9 "$P" 2>/dev/null; stopts; echo "INVALID not-ready" > "$R/outcome"; log "END $L INVALID-notready"; exit 1; fi
log "ready"
ps -o args= -p "$P" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|AlwaysPreTouch' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
grep -h "Node configuration" "$R/logs/system.log" | grep -o "authenticator=[^;]*;\|authorizer=[^;]*;\|role_manager=[^;]*;\|in_select_cartesian_product_[a-z_]*=[^;]*;" | sort -u | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 < /dev/null > "$R/sampler.out" 2>&1 & echo $! > "$R/jstat.pid" )
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do echo \"\$(date +%s) \$(awk '/RssAnon/{print \$2}' /proc/$P/status 2>/dev/null)\" >> $R/rss.txt; cat /sys/fs/cgroup$CGP/memory.events > $R/memory.events.last 2>/dev/null; sleep 5; done" < /dev/null > /dev/null 2>&1 & echo $! > "$R/rss.pid" )
( setsid nohup bash -c "while kill -0 $P 2>/dev/null; do if grep -q -m1 'Pause Full (G1 Humongous Allocation)' $R/gc.log 2>/dev/null; then date +%s.%N > $R/threads-hum.at; timeout 120 jcmd $P Thread.print > $R/threads-hum.txt 2>&1; date +%s.%N >> $R/threads-hum.at; break; fi; sleep 1; done" < /dev/null > /dev/null 2>&1 & echo $! > "$R/hum.pid" )
stopsamplers(){ touch "$R/sampler.stop"; sleep 1; kill "$(cat "$R/jstat.pid")" "$(cat "$R/rss.pid")" 2>/dev/null; kill -- -"$(cat "$R/hum.pid")" 2>/dev/null; stopts; }
stopnode(){ if alive; then kill "$P"; for i in $(seq 1 30); do alive || break; sleep 1; done; alive && { kill -9 "$P"; log "SIGKILL after 30 s"; }; fi; }
# --- superuser: roles, the admin schema (+ the case's one row), grants (only these) ---
for i in $(seq 1 30); do su_cql "SELECT role FROM system_auth.roles" > /dev/null 2>&1 && break; sleep 2; done
{
log "superuser setup"
su_cql "CREATE ROLE $ATK_U WITH LOGIN = true AND PASSWORD = '$ATK_P';
CREATE ROLE $VIC_U WITH LOGIN = true AND PASSWORD = '$VIC_P';
CREATE ROLE $NG_U WITH LOGIN = true AND PASSWORD = '$NG_P';
CREATE KEYSPACE u5 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE u5.ck (pk int, c1 int, c2 int, v int, PRIMARY KEY (pk, c1, c2));
INSERT INTO u5.ck (pk, c1, c2, v) VALUES (0, 0, 0, 1);
CREATE KEYSPACE vk WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE vk.kv (k int PRIMARY KEY, v blob);
GRANT SELECT ON TABLE u5.ck TO $ATK_U;
GRANT SELECT ON TABLE vk.kv TO $VIC_U;
GRANT MODIFY ON TABLE vk.kv TO $VIC_U;"
su_cql "LIST ROLES; LIST ALL PERMISSIONS OF $ATK_U; LIST ALL PERMISSIONS OF $VIC_U; LIST ALL PERMISSIONS OF $NG_U;"
sleep 3
log "attacker privilege checks (expected: Unauthorized x4)"
as_cql $ATK_U $ATK_P "SELECT * FROM vk.kv LIMIT 1;" 2>&1 | tail -1
as_cql $ATK_U $ATK_P "INSERT INTO u5.ck (pk, c1, c2, v) VALUES (1, 1, 1, 1);" 2>&1 | tail -1
as_cql $ATK_U $ATK_P "CREATE KEYSPACE atkks WITH replication = {'class':'SimpleStrategy','replication_factor':1};" 2>&1 | tail -1
as_cql $ATK_U $ATK_P "ALTER TABLE u5.ck WITH comment='x';" 2>&1 | tail -1
log "attacker allowed read (expected: 1 row)"
as_cql $ATK_U $ATK_P "SELECT * FROM u5.ck WHERE pk = 0 AND c1 IN (0,1) AND c2 IN (0,1);" 2>&1 | tail -3
log "no-grant login probe (small, not an attack): system_schema.columns IN x IN (expected rows) and u5.ck (expected Unauthorized)"
as_cql $NG_U $NG_P "SELECT keyspace_name, table_name, column_name FROM system_schema.columns WHERE keyspace_name = 'u5' AND table_name IN ('ck','zz') AND column_name IN ('c1','c2','v');" 2>&1 | tail -8
as_cql $NG_U $NG_P "SELECT * FROM u5.ck WHERE pk = 0;" 2>&1 | tail -1
log "pre-auth check: QUERY before AUTH_RESPONSE (expected: error, no rows)"
python3 - <<'EOF'
import socket, struct
s = socket.create_connection(('127.0.0.1', 9042), timeout=5)
f = lambda st, op, b: struct.pack('>BBhBi', 4, 0, st, op, len(b)) + b
m = struct.pack('>H', 1) + struct.pack('>H', 11) + b'CQL_VERSION' + struct.pack('>H', 5) + b'3.0.0'
s.sendall(f(0, 1, m)); h = s.recv(9); op = h[4]; s.recv(struct.unpack('>i', h[5:9])[0])
q = b'SELECT * FROM u5.ck WHERE pk = 0'
s.sendall(f(1, 7, struct.pack('>i', len(q)) + q + struct.pack('>HB', 1, 0)))
h = s.recv(9); ln = struct.unpack('>i', h[5:9])[0]; b = b''
while len(b) < ln:
    c = s.recv(ln - len(b))
    if not c: break
    b += c
print('pre-auth: STARTUP ->', 'AUTHENTICATE' if op == 3 else op, '; QUERY -> opcode', h[4], 'len', ln, b[6:140].decode(errors='replace'))
EOF
log "attacker small CK request through the case client as $ATK_U (4 x 4, expected 1 row)"
python3 "$H/u5client.py" run --cond CK --k1 4 --k2 4 --window 30 --out "$R/precheck.jsonl" --user $ATK_U --pw $ATK_P; cat "$R/precheck.jsonl"
log "no-grant role through the case client on u5.ck (expected pre_send_error Unauthorized)"
python3 "$H/u5client.py" run --cond CK --k1 4 --k2 4 --window 30 --out "$R/precheck-nogrant.jsonl" --user $NG_U --pw $NG_P; cat "$R/precheck-nogrant.jsonl"
} > "$R/auth-setup.txt" 2>&1
cat "$R/auth-setup.txt"
sleep 3; timeout 120 jcmd "$P" GC.class_histogram > "$R/histo-baseline.txt" 2>&1; tail -1 "$R/histo-baseline.txt"
# --- victim tenant: 10 ops/s on its own table, from 60 s before the attack to 60 s after the endpoint ---
( C2_USER=$VIC_U C2_PASS=$VIC_P setsid nohup python3 "$H/victim.py" $IP 10 3000 2 > "$R/victim.csv" 2> "$R/victim.err" < /dev/null & echo $! > "$R/victim.pid" )
log "victim tenant client started (pid $(cat "$R/victim.pid"))"
sleep 60
log "ATTACK START (as $ATK_U): one EXECUTE, c1 IN ($K1) x c2 IN ($K2)"
date +%s.%N > "$R/attack_start"
( setsid nohup python3 "$H/u5client.py" run --cond CK --k1 "$K1" --k2 "$K2" --window "$WIN" --out "$R/client.jsonl" --user $ATK_U --pw $ATK_P < /dev/null > "$R/client.err" 2>&1 & echo $! > "$R/client.pid" )
CP=$(cat "$R/client.pid")
for i in $(seq 1 240); do grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null && break; kill -0 "$CP" 2>/dev/null || break; sleep 0.5; done
if ! grep -q '"ev": "sent"' "$R/client.jsonl" 2>/dev/null; then log "client did not send"; cat "$R/client.jsonl" "$R/client.err"; kill "$(cat "$R/victim.pid")"; stopnode; stopsamplers; echo "INVALID no-send" > "$R/outcome"; log "END $L INVALID-nosend"; exit 1; fi
TSMS=$(python3 -c "import json,sys; print([json.loads(l) for l in open(sys.argv[1]) if '\"sent\"' in l][0]['t_send_ms'])" "$R/client.jsonl")
TS=$(( TSMS / 1000 )); echo "$TSMS" > "$R/t_send_ms"
log "sent: $(grep '"ev": "sent"' "$R/client.jsonl")"
( sleep 2; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t2.txt" 2>&1; sleep 4; alive && timeout 30 jcmd "$P" Thread.print > "$R/threads-t6.txt" 2>&1 ) &
( sleep 4; timeout 20 "$TREE/bin/cqlsh" $IP -u cassandra -p cassandra -e "SELECT address, port, username, request_count FROM system_views.clients;" > "$R/clients-view.txt" 2>&1 ) &
dead=0; cend=""; thrown=""; dumpd=""; why=""
ooml(){ grep -F -m1 'java.lang.OutOfMemoryError: ' "$R/stdout.ts" 2>/dev/null; }
while true; do
  sleep 2; el=$(( $(date +%s) - TS ))
  if [ -z "$thrown" ] && ooml >/dev/null; then thrown=$el; log "THROWN seen at +${el}s: $(ooml | cut -c1-200)"; fi
  if [ -n "$thrown" ] && [ -z "$dumpd" ] && grep -q 'Heap dump file created' "$R/stdout.ts" 2>/dev/null; then dumpd=$el; log "dump done seen at +${el}s"; fi
  if ! alive; then dead=1; log "VICTIM NODE DEAD at +${el}s"; date +%s.%N > "$R/dead_detected"; break; fi
  if [ -n "$thrown" ]; then
    [ $(( el - thrown )) -ge "$GRACE" ] && { why="grace over after throw"; log "$why"; break; }
  else
    if ! kill -0 "$CP" 2>/dev/null; then
      [ -z "$cend" ] && { cend=$el; log "client ended at +${el}s: $(tail -1 "$R/client.jsonl")"; }
      [ $(( el - cend )) -ge 15 ] && { why="client end + 15 s"; break; }
    fi
    [ $el -ge "$WIN" ] && { why="window W over (no throw)"; log "$why"; break; }
  fi
  [ $(( el % 20 )) -lt 2 ] && log "+${el}s jmx: $(tail -1 "$R/samples.csv" | cut -c1-120) | tenant: $(tail -1 "$R/victim.csv" | cut -c1-120)"
done
wait 2>/dev/null
sleep 2; kill "$CP" 2>/dev/null
cp "$R/memory.events.last" "$R/memory.events" 2>/dev/null
if [ $dead = 0 ]; then log "node alive at lifetime end; tenant 60 s more before stopping it"; fi
log "victim tenant: 60 s after"; sleep 60
kill "$(cat "$R/victim.pid")" 2>/dev/null; sleep 1; tail -2 "$R/victim.csv"
stopnode; JEXIT=$(date +%s.%N); stopsamplers
cat "$UCG/memory.events" > "$R/parent.memory.events.after" 2>/dev/null
OOMT=$(grep -h -o -m1 "java.lang.OutOfMemoryError: [A-Za-z ]*" "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -1)
CL=$(grep -v '"ev": "prepared"\|"ev": "sent"' "$R/client.jsonl" | tail -1)
REL=$(python3 - "$R" "$TSMS" <<'EOF'
import sys
R, ts = sys.argv[1], int(sys.argv[2]) / 1000
def first(pat):
    try:
        for l in open(R + '/stdout.ts', errors='replace'):
            if pat in l: return '%+.1fs' % (float(l.split(' ', 1)[0]) - ts)
    except FileNotFoundError: pass
    return '-'
try: dd = '%+.1fs' % (float(open(R + '/dead_detected').read()) - ts)
except Exception: dd = '-'
print('thrown_at=%s dump_done_at=%s kill9_at=%s dead_detected_at=%s' % (first('java.lang.OutOfMemoryError: '), first('Heap dump file created'), first('Executing /bin/sh -c "kill -9'), dd))
EOF
)
if [ -n "$OOMT" ]; then echo "OOM type=\"$OOMT\" $REL client=$CL" > "$R/outcome"
elif [ $dead = 1 ]; then echo "DEAD-noOOM $REL client=$CL" > "$R/outcome"
else echo "SURVIVED $REL end=\"$why\" client=$CL" > "$R/outcome"; fi
cat "$R/outcome"
grep -h -m3 -B2 -A30 'java\.lang\.OutOfMemoryError: ' "$R/stdout.log" "$R/logs/system.log" 2>/dev/null | head -150 > "$R/oom-excerpt.txt"
grep -h 'Dumping heap\|Heap dump file\|Executing /bin/sh' "$R/stdout.log" >> "$R/oom-excerpt.txt" 2>/dev/null
grep -h 'OutOfMemoryError: \|Dumping heap\|Heap dump file\|Executing /bin/sh\|ERROR\|WARN' "$R/stdout.ts" 2>/dev/null | cut -c1-400 | head -60 > "$R/stdout-ts-excerpt.txt"
grep -h -i 'operations were slow\|timed out\|cartesian\|guardrail\|InvalidRequest\|Unauthorized' "$R/logs/system.log" "$R/logs/debug.log" 2>/dev/null | cut -c1-600 | head -20 > "$R/monitor-guard-excerpt.txt"
for t in t2 t6 hum; do [ -f "$R/threads-$t.txt" ] && grep -A40 '"Native-Transport-Requests' "$R/threads-$t.txt" | grep -B3 -A30 'MultiCBuilder\|SelectStatement\|BTree\|CBuilder' | head -80 > "$R/ntr-$t.txt"; done
grep -h 'Pause\|Humongous\|humongous' "$R"/gc.log* 2>/dev/null | grep -v 'safepoint' | tail -40 > "$R/gc-tail.txt"
grep -h 'Pause Full' "$R"/gc.log* 2>/dev/null > "$R/gc-full.txt"
python3 "$H/gcwin.py" "$R" > "$R/gcwin.txt" 2>&1
ls -la "$R" | grep -i 'hprof\|hs_err' > "$R/hprof.ls"
log "java left: $(pgrep -af java | grep -v pgrep | cut -c1-120 || echo none)"
log "END $L $(cat "$R/outcome" | cut -c1-300)"
