#!/usr/bin/env bash
# One cluster-tier arm (case B3, amended 2026-10-26). Port slot 5: node on 127.0.5.1, JMX 7150, Byteman agent 19150.
# usage: bash cluster-run.sh LABEL L ARM [live]
#   L   = yaml value for native_transport_max_request_data_in_flight (and _per_ip), e.g. 16MiB, 1GiB, or "default"
#         (global key absent = maxMemory/10; per_ip pinned to 107374182B)
#   ARM = v4-256k | v5-256k | v5-100k      live = start at L (1GiB), set 16MiB through JMX at LIVE_AT seconds of load
# env: LOAD_S (90; live: 120)  LIVE_AT (30)  BASE_S (30)  TAG_DIR (~/s4-b8-cr-logs/cluster)
# Logs every command with an epoch-ms stamp to $OUT/run.log; stops the node on any exit; stops at a failed first-trigger check.
set -uo pipefail
LABEL=$1; L=$2; ARM=$3; LIVE=${4:-}
CL=$HOME/s4-b8-cr; H=$HOME/s4-b8-cr-harness; NODE=$HOME/s4-b8-cr-node
DD=/dev/shm/s4-b8-cr-data; ADDR=127.0.5.1; JMXP=7150; BMP=19150
OUT=${TAG_DIR:-$HOME/s4-b8-cr-logs/cluster}/$LABEL
LOAD_S=${LOAD_S:-90}; [ -n "$LIVE" ] && LOAD_S=${LOAD_S_LIVE:-120}; LIVE_AT=${LIVE_AT:-30}; BASE_S=${BASE_S:-30}
BM=$CL/build/lib/jars/byteman-4.0.20.jar
case $ARM in
  v4-256k) VER=4; BLOB=262144; W=250;;
  v5-256k) VER=5; BLOB=262144; W=250;;
  v5-100k) VER=5; BLOB=100000; W=640;;
  *) echo "bad ARM"; exit 2;;
esac
C=4
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
run() { log "+ $*"; "$@"; }
die() { log "FAIL: $*"; exit 1; }
nodetool() { "$CL/bin/nodetool" -h 127.0.0.1 -p $JMXP "$@"; }

node_pids() {   # java processes running CassandraDaemon from this tree
  local p
  for p in $(pgrep -x java); do
    tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q CassandraDaemon || continue
    tr '\0' ' ' < /proc/$p/cmdline | grep -q "$CL/" && echo $p
  done
}
PROBE_PID=; NMT_PID=; HIST_PID=; CLIENT_PID=; LIVE_PID=
stop_node() {
  local pids; pids=$(node_pids)
  [ -n "$pids" ] || { log "no node running"; return 0; }
  log "stopping node pids: $pids"; kill $pids
  for i in $(seq 1 120); do [ -z "$(node_pids)" ] && break; sleep 1; done
  pids=$(node_pids); [ -n "$pids" ] && { log "node still up after 120 s, kill -9 $pids"; kill -9 $pids; sleep 2; }
  [ -z "$(node_pids)" ] && log "node stopped; none left" || log "WARNING: node still present"
}
cleanup() {
  for p in $NMT_PID $HIST_PID $PROBE_PID $CLIENT_PID $LIVE_PID; do [ -n "$p" ] && kill $p 2>/dev/null; done
  rm -f "$OUT/hold.flag"
  stop_node
  rm -rf "$DD"
  log "END $LABEL"
}
trap cleanup EXIT

log "START $LABEL L=$L ARM=$ARM(version $VER, blob $BLOB, C=$C, W=$W) live=${LIVE:-no} LOAD_S=$LOAD_S BASE_S=$BASE_S"
run git -C "$CL" describe --tags
run sha256sum "$H"/cluster-run.sh "$H"/NativeFlood.java "$H"/InflightProbe.java "$H"/hold-request.btm "$H"/reduce.py

# step 1: nothing of ours running; ports free; empty data on tmpfs
[ -z "$(node_pids)" ] || die "a node from $CL is already running: $(node_pids)"
for port in 9042 7000; do ss -ltn | grep -q "$ADDR:$port " && die "port $ADDR:$port in use"; done
for port in $JMXP $BMP; do ss -ltn | grep -qE "[:.]$port " && die "port $port in use"; done
run rm -rf "$DD"; run mkdir -p "$DD"/{data,commitlog,hints,saved_caches,cdc_raw}

# step 2: conf dir = the tag's conf with this arm's yaml lines and JMX port 7150
rm -rf "$NODE"; mkdir -p "$NODE/logs"; cp -r "$CL/conf" "$NODE/conf"
git -C "$CL" show HEAD:conf/cassandra.yaml > "$OUT/shipped.yaml"
git -C "$CL" show HEAD:conf/cassandra-env.sh | sed "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMXP\"/" > "$NODE/conf/cassandra-env.sh"
grep -n '^JMX_PORT' "$NODE/conf/cassandra-env.sh"
python3 - "$OUT/shipped.yaml" "$NODE/conf/cassandra.yaml" "$L" "$LIVE" "$DD" "$ADDR" <<'PY'
import re, sys
src, dst, L, live, dd, addr = sys.argv[1:]
add = ['cluster_name: s4-cr', 'num_tokens: 1', 'auto_bootstrap: false', 'listen_address: ' + addr, 'rpc_address: ' + addr,
       'native_transport_port: 9042', 'seed_provider:', '  - class_name: org.apache.cassandra.locator.SimpleSeedProvider',
       '    parameters:', '      - seeds: "%s:7000"' % addr]
if L == 'default':
    add.append('native_transport_max_request_data_in_flight_per_ip: 107374182B')
else:
    v = '1GiB' if live else L
    add += ['native_transport_max_request_data_in_flight: ' + v, 'native_transport_max_request_data_in_flight_per_ip: ' + v]
add += ['native_transport_max_message_size: 1MiB', 'native_transport_max_threads: 4', 'native_transport_receive_queue_capacity: 1MiB',
        'native_transport_throw_on_overload: false', 'native_transport_rate_limiting_enabled: false',
        'native_transport_timeout: 600000ms', 'read_request_timeout: 600000ms', 'write_request_timeout: 600000ms', 'auto_snapshot: false',
        'data_file_directories:', '    - %s/data' % dd, 'commitlog_directory: %s/commitlog' % dd, 'hints_directory: %s/hints' % dd,
        'saved_caches_directory: %s/saved_caches' % dd, 'cdc_raw_directory: %s/cdc_raw' % dd]
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(src).read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == '' or l.lstrip().startswith('#')):
        continue
    else:
        skip = False
    out.append(l)
open(dst, 'w').write('\n'.join(out) + '\n# ---- stage4 cr lines ----\n' + '\n'.join(add) + '\n')
PY
[ $? -eq 0 ] || die "yaml edit failed"
diff "$OUT/shipped.yaml" "$NODE/conf/cassandra.yaml" > "$OUT/yaml.diff"; log "yaml diff saved ($(wc -l < "$OUT/yaml.diff") lines)"
sed -n '/^# ---- stage4 cr lines/,$p' "$NODE/conf/cassandra.yaml" | grep -E 'request_data|message_size|max_threads|timeout|receive_queue' | sed 's/^/yaml: /'

# step 3: start the node (Byteman agent with the hold rule; Netty on JDK direct buffers; NMT)
EXTRA="-Dio.netty.maxDirectMemory=0 -XX:MaxDirectMemorySize=4g -XX:NativeMemoryTracking=summary -Dstage4.hold.file=$OUT/hold.flag -Dstage4.hold.ms=100 -Dstage4.trace=$OUT/hold.trace -javaagent:$BM=port:$BMP,address:127.0.0.1,script:$H/hold-request.btm,listener:true"
cd "$CL" || die "no tree"
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
log "+ CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$OUT/logs MAX_HEAP_SIZE=1G JVM_EXTRA_OPTS=\"$EXTRA\" bin/cassandra -p $OUT/cassandra.pid"
T0=$(date +%s)
CASSANDRA_CONF="$NODE/conf" CASSANDRA_LOG_DIR="$OUT/logs" MAX_HEAP_SIZE=1G JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p "$OUT/cassandra.pid" > "$OUT/cassandra.out" 2>&1
up=0
for i in $(seq 1 90); do
  sleep 2
  [ -n "$(node_pids)" ] || die "daemon died during start (see $OUT/logs/system.log)"
  if nodetool status 2>/dev/null | grep -q '^UN' && [ "$(nodetool statusbinary 2>/dev/null)" = running ]; then up=1; break; fi
done
[ $up = 1 ] || die "node not UN + binary running within 180 s"
PID=$(node_pids); log "node up after $(( $(date +%s) - T0 )) s, pid $PID"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E 'maxDirectMemory|NativeMemoryTracking|Xmx|Xms|MaxDirectMemorySize|javaagent|stage4' | sed 's/^/jvm-arg: /'
GL=$(nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytes 2>/dev/null | tail -1); log "global limit at start: $GL"
GP=$(nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytesPerIp 2>/dev/null | tail -1); log "per-IP limit at start: $GP"
echo "global_limit_start=$GL" > "$OUT/limits.txt"; echo "per_ip_limit_start=$GP" >> "$OUT/limits.txt"
[ "$L" = default ] && { [ "$GL" = 107374182 ] || die "default arm: global limit $GL != 107374182 (heap/10)"; }
run java -cp "$BM:$CL/build/lib/jars/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -p $BMP -l | tee "$OUT/byteman-list.txt" | head -8
grep -q 'ntq hold request' "$OUT/byteman-list.txt" || die "hold rule not loaded"

# step 4: schema, client classes, warm-up, settle, idle baseline
run "$CL/bin/cqlsh" $ADDR 9042 -e "CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE IF NOT EXISTS ks.t (pk int PRIMARY KEY, v blob);" || die "schema failed"
mkdir -p "$H/classes"
CP="$H/classes:$CL/build/classes/main:$CL/build/lib/jars/*:$CL/lib/*"
CJ=$(grep -v '^#' "$CL/conf/jvm11-clients.options" | grep -v '^$' | tr '\n' ' ')
mkdir -p "$H/probe"; javac -d "$H/probe" "$H/InflightProbe.java" || die "probe compile"
[ -f "$H/classes/org/apache/cassandra/transport/NativeFlood.class" ] || javac -cp "$CP" -d "$H/classes" "$H/NativeFlood.java" || die "client compile"
flood() { java $CJ -Dio.netty.eventLoopThreads=1 -Dlogback.configurationFile=$H/flood-logback.xml -Xmx2g -cp "$CP" org.apache.cassandra.transport.NativeFlood --host $ADDR "$@"; }
log "warm-up flood (no hold; 20000-B values, below LARGE_MESSAGE_THRESHOLD, so a v5 arm does not start with a frame-buffer residue)"
flood --connections 1 --window 4 --value-bytes 20000 --seconds 5 --throw false --version $VER > "$OUT/warmup.txt" 2>&1; tail -2 "$OUT/warmup.txt"
sleep 10
HIST() { jcmd "$PID" GC.class_histogram 2>/dev/null | tail -1; }
log "+ java -cp $H InflightProbe 127.0.0.1 $JMXP 200 $((BASE_S*1000)) > $OUT/base.csv"
( echo "t=$(date +%s%3N) baseline"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other' ) > "$OUT/nmt-base.txt" 2>&1
java -cp "$H/probe" InflightProbe 127.0.0.1 $JMXP 200 $((BASE_S*1000)) > "$OUT/base.csv" || die "baseline probe failed"
echo "hist_baseline: $(HIST)" | tee "$OUT/hist.txt"
log "baseline rows: $(($(wc -l < "$OUT/base.csv") - 1))"

# step 5: probe, NMT loop, histogram at 60 s of load, optional live change
PROBE_MS=$(( (LOAD_S + 150) * 1000 ))
java -cp "$H/probe" InflightProbe 127.0.0.1 $JMXP 200 $PROBE_MS > "$OUT/run.csv" & PROBE_PID=$!
PROBE_T0=$(date +%s%3N); log "probe started pid $PROBE_PID at $PROBE_T0"
( while sleep 2; do echo "t=$(date +%s%3N)"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other'; done ) > "$OUT/nmt.txt" 2>&1 & NMT_PID=$!
sleep 1

# step 6: workload (hold flag on)
touch "$OUT/hold.flag"
CT0=$(date +%s%3N); log "client start $CT0 (hold flag on)"
echo "probe_start_ms=$PROBE_T0 client_start_ms=$CT0" > "$OUT/times.txt"
flood --connections $C --window $W --value-bytes $BLOB --seconds $LOAD_S --throw false --version $VER > "$OUT/client.txt" 2>&1 & CLIENT_PID=$!
( sleep 60; if [ "${HIST_TOP:-0}" = 1 ]; then HH=$(jcmd "$PID" GC.class_histogram 2>/dev/null); echo "$HH" | head -18 > "$OUT/hist-top-load60.txt"; echo "hist_load60: $(echo "$HH" | tail -1)" >> "$OUT/hist.txt"; else echo "hist_load60: $(HIST)" >> "$OUT/hist.txt"; fi ) & HIST_PID=$!   # HIST_TOP=1 (diagnostic arms after run 1 only): also keep the top of the histogram
if [ -n "$LIVE" ]; then
  ( sleep $LIVE_AT; echo "live_set_ms=$(date +%s%3N)" >> "$OUT/times.txt"
    nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -f NativeTransportMaxConcurrentRequestsInBytes -v 16777216 -ms > "$OUT/live-set.txt" 2>&1
    echo "live_set_done_ms=$(date +%s%3N)" >> "$OUT/times.txt"
    nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytes >> "$OUT/live-set.txt" 2>&1 ) & LIVE_PID=$!
fi
# first-trigger check: the hold rule fires and the counter leaves zero within 15 s
ok=0; for i in $(seq 1 15); do sleep 1; if [ -s "$OUT/hold.trace" ] && awk -F, 'NR>1 && $2>0 {f=1} END{exit !f}' "$OUT/run.csv"; then ok=1; break; fi; done
[ $ok = 1 ] || die "first-trigger check failed: no hold line in hold.trace or RequestsSize stayed 0 within 15 s"
log "first trigger ok: $(wc -l < "$OUT/hold.trace") hold lines; RequestsSize seen > 0"
echo "EXPECTED: first trigger: hold rule fired and RequestsSize > 0 within 15 s: PASS"
wait $CLIENT_PID; CRC=$?; CLIENT_PID=
CT1=$(date +%s%3N); log "client end $CT1 (rc $CRC, elapsed $(( CT1 - CT0 )) ms)"
echo "client_end_ms=$CT1 client_rc=$CRC" >> "$OUT/times.txt"
[ -n "$LIVE_PID" ] && { wait $LIVE_PID 2>/dev/null; LIVE_PID=; }
sleep 3
rm -f "$OUT/hold.flag"; kill $PROBE_PID $NMT_PID 2>/dev/null; wait $PROBE_PID 2>/dev/null; PROBE_PID=; NMT_PID=
wait $HIST_PID 2>/dev/null; HIST_PID=
run nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -mg -f Value
grep -cE '^(ERROR|WARN)' "$OUT/logs/system.log" | sed 's/^/system.log ERROR+WARN lines: /'
grep -E '^ERROR' "$OUT/logs/system.log" | head -5
grep -c 'LEAK:' "$OUT/logs/system.log" | sed 's/^/netty LEAK lines: /'
grep -c 'hold' "$OUT/hold.trace" | sed 's/^/hold lines: /'

# step 7: stop the node, reduce
stop_node
run python3 "$H/reduce.py" "$OUT" "$L" "$ARM" "${LIVE:-no}" | tee "$OUT/summary.txt"
