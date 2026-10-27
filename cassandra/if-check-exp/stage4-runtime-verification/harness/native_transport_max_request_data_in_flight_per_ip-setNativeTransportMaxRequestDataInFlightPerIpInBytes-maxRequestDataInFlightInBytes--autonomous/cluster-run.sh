#!/usr/bin/env bash
# One cluster-tier run of the case file (B3e with the 2026-10-26 audit amendments). Slot 4, node pc12.
# usage: bash cluster-run.sh LABEL PROTO GLOBAL PERIP THREADS PER_THREAD
#   PROTO = 4|5; GLOBAL, PERIP = yaml values (e.g. 1GiB, 8MiB); THREADS connections from 127.0.4.1, each PER_THREAD INSERTs
# env: SRC2THREADS (0) extra threads bound to 127.0.4.3 (run r8); JMXSET (0) bytes to set over JMX once RequestsSize first passes 100 MiB (r9);
#      TAIL_S (30) seconds the probe keeps running after the load; BLOB (4194304); HOLD (1; 0 = no Byteman rule, only for step-1 checks)
# Logs every command with an epoch-ms stamp to ~/s4-b8-pi-logs/cluster/LABEL/run.log; stops the node on any exit (by PID).
set -uo pipefail
LABEL=$1; PROTO=$2; GL=$3; PI=$4; TH=$5; PER=$6
SRC2THREADS=${SRC2THREADS:-0}; JMXSET=${JMXSET:-0}; TAIL_S=${TAIL_S:-30}; BLOB=${BLOB:-4194304}; HOLD=${HOLD:-1}
CL=$HOME/s4-b8-pi; TOOLS=$HOME/s4-b8-pi-harness; DD=/dev/shm/s4-b8-pi
OUT=$HOME/s4-b8-pi-logs/cluster/$LABEL
ADDR=127.0.4.1; JMXP=7140; BM=$CL/build/lib/jars/byteman-4.0.20.jar
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
run() { log "+ $*"; "$@"; }
die() { log "FAIL: $*"; exit 1; }
NT="$CL/bin/nodetool -h 127.0.0.1 -p $JMXP"

node_pids() {   # java processes running CassandraDaemon from this working tree
  local p
  for p in $(pgrep -x java); do
    tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q CassandraDaemon || continue
    if [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$CL" ] || tr '\0' ' ' < /proc/$p/cmdline | grep -q "$CL/"; then echo $p; fi
  done
}
PROBE_PID=; NMT_PID=; LOAD_PID=; WATCH_PID=
stop_node() {
  local pids; pids=$(node_pids)
  [ -n "$pids" ] || { log "no node running"; return 0; }
  log "stopping node pids: $pids"; kill $pids
  for i in $(seq 1 120); do [ -z "$(node_pids)" ] && break; sleep 1; done
  pids=$(node_pids); [ -n "$pids" ] && { log "node still up after 120 s, kill -9 $pids"; kill -9 $pids; sleep 2; }
  [ -z "$(node_pids)" ] && log "node stopped; none left" || log "WARNING: node still present"
}
cleanup() {
  for p in $NMT_PID $PROBE_PID $LOAD_PID $WATCH_PID; do [ -n "$p" ] && kill $p 2>/dev/null; done
  stop_node
  log "END $LABEL"
}
trap cleanup EXIT

log "START $LABEL PROTO=$PROTO GLOBAL=$GL PERIP=$PI THREADS=$TH PER_THREAD=$PER SRC2THREADS=$SRC2THREADS JMXSET=$JMXSET TAIL_S=$TAIL_S BLOB=$BLOB HOLD=$HOLD"
run git -C "$CL" describe --tags; run git -C "$CL" rev-parse HEAD
run sha256sum "$TOOLS"/loadgen.py "$TOOLS"/PiProbe.java "$TOOLS"/JmxSet.java "$TOOLS"/hold.btm "$TOOLS"/cluster-run.sh

# step 1: no node running from this tree; ports free; empty data
[ -z "$(node_pids)" ] || die "a node from $CL is already running: $(node_pids)"
for i in $(seq 1 60); do ss -ltn | grep -qE "(127.0.4.1:(7000|9042)|:$JMXP) " || break; sleep 1; done
ss -ltn | grep -qE "(127.0.4.1:(7000|9042)|:$JMXP) " && die "slot 4 port in use"
run rm -rf "$DD"; run mkdir -p "$DD"/{data,commitlog,hints,saved_caches,cdc_raw}; rm -rf "$OUT/logs"
grep -q '^JMX_PORT="7140"' "$CL/conf/cassandra-env.sh" || sed -i 's/^JMX_PORT="7199"/JMX_PORT="7140"/' "$CL/conf/cassandra-env.sh"
grep -n '^JMX_PORT' "$CL/conf/cassandra-env.sh"

# step 2: yaml = the tag's file with B3a's edits
git -C "$CL" show HEAD:conf/cassandra.yaml > "$OUT/shipped.yaml"
python3 - "$OUT/shipped.yaml" "$CL/conf/cassandra.yaml" "$GL" "$PI" "$DD" "$ADDR" <<'PY'
import re, sys
src, dst, GL, PI, dd, addr = sys.argv[1:]
add = ['native_transport_max_request_data_in_flight: ' + GL, 'native_transport_max_request_data_in_flight_per_ip: ' + PI,
       'native_transport_receive_queue_capacity: 64KiB', 'native_transport_max_message_size: 8MiB',
       'commitlog_total_space: 512MiB', 'max_mutation_size: 16MiB',
       'write_request_timeout: 600000ms', 'native_transport_timeout: 600000ms', 'auto_snapshot: false',
       'listen_address: ' + addr, 'rpc_address: ' + addr,
       'data_file_directories:', '    - %s/data' % dd, 'commitlog_directory: %s/commitlog' % dd,
       'hints_directory: %s/hints' % dd, 'saved_caches_directory: %s/saved_caches' % dd, 'cdc_raw_directory: %s/cdc_raw' % dd]
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
out, skip = [], False
for l in open(src).read().splitlines():
    l = re.sub(r'(- seeds:).*', r'\1 "%s:7000"' % addr, l)
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''):
        continue
    else:
        skip = False
    out.append(l)
open(dst, 'w').write('\n'.join(out) + '\n# ---- stage4 pi lines ----\n' + '\n'.join(add) + '\n')
PY
[ $? -eq 0 ] || die "yaml edit failed"
run grep -nE 'request_data_in_flight|receive_queue|max_message_size|commitlog_total|max_mutation|write_request_timeout|native_transport_timeout|auto_snapshot|_address|seeds|_directory|data_file' "$CL/conf/cassandra.yaml"
diff "$OUT/shipped.yaml" "$CL/conf/cassandra.yaml" > "$OUT/yaml.diff"; log "yaml diff saved ($(wc -l < "$OUT/yaml.diff") lines)"

# step 3: start the node
EXTRA="-Dio.netty.maxDirectMemory=0 -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=8g"
[ "$HOLD" = 1 ] && EXTRA="$EXTRA -javaagent:$BM=script:$TOOLS/hold.btm"
cd "$CL" || die "no tree"
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
log "+ CASSANDRA_LOG_DIR=$OUT/logs MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS=\"$EXTRA\" bin/cassandra -p $OUT/cassandra.pid"
T0=$(date +%s)
CASSANDRA_LOG_DIR="$OUT/logs" MAX_HEAP_SIZE=2G JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p "$OUT/cassandra.pid" > "$OUT/cassandra.out" 2>&1
up=0
for i in $(seq 1 120); do
  sleep 3
  [ -n "$(node_pids)" ] || die "daemon died during start (see $OUT/logs/system.log, $OUT/cassandra.out)"
  if $NT status 2>/dev/null | grep -q '^UN' && [ "$($NT statusbinary 2>/dev/null)" = running ]; then up=1; break; fi
done
[ $up = 1 ] || die "node not UN + binary running within 360 s"
PID=$(node_pids); log "node up after $(( $(date +%s) - T0 )) s, pid $PID"
run $NT status
tr '\0' '\n' < /proc/$PID/cmdline | grep -E 'maxDirectMemory|NativeMemoryTracking|Xmx|Xms|UseG1GC|MaxDirectMemorySize|javaagent:.*byteman' | sed 's/^/jvm-arg: /'
run jcmd $PID VM.flags | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|MaxHeapSize' | sed 's/^/jvm-flag: /'
run $NT sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytes
run $NT sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytesPerIp
grep -E 'native_transport_max_request|Byteman|byteman' "$OUT/logs/system.log" "$OUT/cassandra.out" | head -5
ss -ltn | grep -E "$ADDR:9042|:$JMXP " | sed 's/^/listen: /'

# step 4: schema, settle, idle baseline (20 s)
export CASSANDRA_HOME=$CL
run python3 -I "$TOOLS/loadgen.py" setup $ADDR 9042 || die "schema setup failed"
run sleep 10
log "+ java -cp $TOOLS PiProbe 127.0.0.1 $JMXP 200 20000 > $OUT/base.csv"
java -cp "$TOOLS" PiProbe 127.0.0.1 $JMXP 200 20000 > "$OUT/base.csv" || die "baseline probe failed"
log "baseline rows: $(($(wc -l < "$OUT/base.csv") - 1))"
( echo "t=$(date +%s%3N) baseline"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other' ) > "$OUT/nmt-base.txt" 2>&1; cat "$OUT/nmt-base.txt"

# step 5: probe + NMT loop (the probe runs until the run ends)
java -cp "$TOOLS" PiProbe 127.0.0.1 $JMXP 200 3600000 > "$OUT/run.csv" & PROBE_PID=$!
PROBE_T0=$(date +%s%3N); log "probe started pid $PROBE_PID at $PROBE_T0"
( while sleep 1; do echo "t=$(date +%s%3N)"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other'; done ) > "$OUT/nmt.txt" 2>&1 & NMT_PID=$!
if [ "$JMXSET" != 0 ]; then
  ( while true; do
      v=$(tail -n 1 "$OUT/run.csv" | python3 -c "import sys; f=sys.stdin.read().strip().split(','); print(f[1] if len(f)>2 and f[1].isdigit() else 0)")
      [ "$v" -ge 104857600 ] && break; sleep 0.5
    done
    log "JMX set trigger: RequestsSize $v"; java -cp "$TOOLS" JmxSet 127.0.0.1 $JMXP "$JMXSET" ) > "$OUT/jmxset.txt" 2>&1 & WATCH_PID=$!
fi
sleep 1

# step 6: workload
CT0=$(date +%s%3N); log "client start $CT0"
EXTRAARGS=; [ "$SRC2THREADS" != 0 ] && EXTRAARGS="127.0.4.3 $SRC2THREADS"
[ "$SRC2THREADS" != 0 ] && ( sleep 25; ss -tn | grep "127.0.4.1:9042" | awk '{print $5}' | sed 's/:[0-9]*$//' | sort | uniq -c > "$OUT/ss-mid.txt" ) &
python3 -I "$TOOLS/loadgen.py" load $ADDR 9042 "$PROTO" "$TH" "$PER" "$BLOB" $EXTRAARGS | tee "$OUT/client.txt"
grep -q '^RESULT' "$OUT/client.txt" || die "client did not complete (no RESULT line; see client.txt)"
CT1=$(date +%s%3N); log "client end $CT1 (elapsed $(( CT1 - CT0 )) ms; probe offset start $(( CT0 - PROBE_T0 )) ms, end $(( CT1 - PROBE_T0 )) ms)"
echo "client_start_ms=$CT0 client_end_ms=$CT1 probe_start_ms=$PROBE_T0" > "$OUT/times.txt"
[ "$SRC2THREADS" != 0 ] && ss -tn 2>/dev/null | grep -c "127.0.4.3:.*127.0.4.1:9042" | sed 's/^/established from 127.0.4.3 at client end (may be 0 after close): /'

# step 7: tail, stop probe and NMT
log "tail ${TAIL_S} s"; for i in $(seq 1 "$TAIL_S"); do sleep 1; done
kill $NMT_PID 2>/dev/null; NMT_PID=; kill $PROBE_PID 2>/dev/null; PROBE_PID=; [ -n "$WATCH_PID" ] && { kill $WATCH_PID 2>/dev/null; WATCH_PID=; }
run $NT sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -mg -f Value
run $NT sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytesPerIp
cat "$OUT/jmxset.txt" 2>/dev/null
grep -cE '^(ERROR|WARN)' "$OUT/logs/system.log" | sed 's/^/system.log ERROR+WARN lines: /'
grep -E '^ERROR' "$OUT/logs/system.log" | head -5
grep -c 'LEAK:' "$OUT/logs/system.log" | sed 's/^/netty LEAK lines: /'

# step 8: stop the node (the trap does it too)
stop_node
# step 9: reduce
log "+ python3 $TOOLS/reduce.py $OUT"
python3 -I "$TOOLS/reduce.py" "$OUT" | tee "$OUT/summary.txt"
