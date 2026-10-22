#!/usr/bin/env bash
# One cluster-tier run of the case file (B3e steps 1-9, with the 2026-10-22 audit amendments).
# usage: bash cluster-run.sh LABEL L C THROW MODE
#   L     = yaml value for native_transport_max_request_data_in_flight (and _per_ip), e.g. 64MiB, 4GiB,
#           or "default" (global unset = heap/10, per_ip pinned to 858993459B)
#   C     = connections; THROW = 0|1; MODE = group|periodic
# env: NREQ (1024), BLOB (1048576), PROBE_MS (480000), NETTY_FLAG (1 = -Dio.netty.maxDirectMemory=0; 0 = omit, step-1 check only)
# Logs every command with an epoch-ms stamp to ~/stage4-logs/pv5/cluster/LABEL/run.log; stops the node on any exit.
set -uo pipefail
LABEL=$1; L=$2; C=$3; T=$4; MODE=$5
CL=$HOME/cassandra-pv5; DD=$HOME/stage4-pv5/data; TOOLS=$HOME/stage4-harness-run/pv5
OUT=$HOME/stage4-logs/pv5/cluster/$LABEL
NREQ=${NREQ:-1024}; BLOB=${BLOB:-1048576}; PROBE_MS=${PROBE_MS:-480000}; NETTY_FLAG=${NETTY_FLAG:-1}
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
run() { log "+ $*"; "$@"; }
die() { log "FAIL: $*"; exit 1; }

node_pids() {   # java processes running CassandraDaemon from this clone (cwd or command line)
  local p
  for p in $(pgrep -x java); do
    tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q CassandraDaemon || continue
    if [ "$(readlink /proc/$p/cwd 2>/dev/null)" = "$CL" ] || tr '\0' ' ' < /proc/$p/cmdline | grep -q "$CL/"; then echo $p; fi
  done
}
PROBE_PID=; NMT_PID=
stop_node() {
  local pids; pids=$(node_pids)
  [ -n "$pids" ] || { log "no node running"; return 0; }
  log "stopping node pids: $pids"; kill $pids
  for i in $(seq 1 120); do [ -z "$(node_pids)" ] && break; sleep 1; done
  pids=$(node_pids); [ -n "$pids" ] && { log "node still up after 120 s, kill -9 $pids"; kill -9 $pids; sleep 2; }
  [ -z "$(node_pids)" ] && log "node stopped; none left" || log "WARNING: node still present"
}
cleanup() {
  [ -n "$NMT_PID" ] && kill $NMT_PID 2>/dev/null
  [ -n "$PROBE_PID" ] && kill $PROBE_PID 2>/dev/null
  pkill -u "$USER" -f "$TOOLS/v4load.py" 2>/dev/null
  stop_node
  log "END $LABEL"
}
trap cleanup EXIT

log "START $LABEL L=$L C=$C THROW=$T MODE=$MODE NREQ=$NREQ BLOB=$BLOB PROBE_MS=$PROBE_MS NETTY_FLAG=$NETTY_FLAG"
run git -C "$CL" describe --tags; run git -C "$CL" rev-parse HEAD
run sha256sum "$TOOLS"/v4load.py "$TOOLS"/InflightProbe.java "$TOOLS"/cluster-run.sh

# step 1: no node running; empty data
[ -z "$(node_pids)" ] || die "a node from $CL is already running: $(node_pids)"
for i in $(seq 1 60); do ss -ltn | grep -qE "[:.](7000|7199|9042) " || break; sleep 1; done
for port in 7000 7199 9042; do ss -ltn | grep -q "[:.]$port " && die "port $port in use"; done
run rm -rf "$DD"; run mkdir -p "$DD"/{data,commitlog,hints,saved_caches,cdc_raw}; rm -rf "$OUT/logs"

# step 2: yaml = the tag's file with B3a's edits (no key twice)
git -C "$CL" show HEAD:conf/cassandra.yaml > "$OUT/shipped.yaml"
python3 - "$OUT/shipped.yaml" "$CL/conf/cassandra.yaml" "$L" "$MODE" "$DD" <<'PY'
import re, sys
src, dst, L, mode, dd = sys.argv[1:]
add = []
if L == 'default':
    add.append('native_transport_max_request_data_in_flight_per_ip: 858993459B')
else:
    add += ['native_transport_max_request_data_in_flight: ' + L, 'native_transport_max_request_data_in_flight_per_ip: ' + L]
if mode == 'group':
    add += ['commitlog_sync: group', 'commitlog_sync_group_window: 10000ms']
add += ['commitlog_segment_size: 1536MiB', 'max_mutation_size: 16MiB']   # runbook defect D1 (2026-10-22): a segment switch forces a sync (AbstractCommitLogSegmentManager.java:334)
add += ['write_request_timeout: 600000ms', 'native_transport_timeout: 600000ms', 'auto_snapshot: false',
        'data_file_directories:', '    - %s/data' % dd, 'commitlog_directory: %s/commitlog' % dd,
        'hints_directory: %s/hints' % dd, 'saved_caches_directory: %s/saved_caches' % dd, 'cdc_raw_directory: %s/cdc_raw' % dd]
keys = {l.split(':', 1)[0] for l in add if re.match(r'^[A-Za-z_]+:', l)}
if mode == 'group':
    keys.add('commitlog_sync_period')      # group mode refuses a period (DatabaseDescriptor.java:517-519)
out, skip = [], False
for l in open(src).read().splitlines():
    m = re.match(r'^([A-Za-z_]+):', l)
    if m:
        skip = m.group(1) in keys
        if skip: continue
    elif skip and (l.startswith((' ', '\t', '-')) or l.strip() == ''):
        continue
    else:
        skip = False
    out.append(l)
open(dst, 'w').write('\n'.join(out) + '\n# ---- stage4 pv5 lines ----\n' + '\n'.join(add) + '\n')
PY
[ $? -eq 0 ] || die "yaml edit failed"
run grep -nE 'request_data_in_flight|commitlog_segment_size|max_mutation_size|commitlog_sync|write_request_timeout|native_transport_timeout|auto_snapshot|_directory|data_file' "$CL/conf/cassandra.yaml"
diff "$OUT/shipped.yaml" "$CL/conf/cassandra.yaml" > "$OUT/yaml.diff"; log "yaml diff saved ($(wc -l < "$OUT/yaml.diff") lines)"

# step 3: start the node
EXTRA="-XX:NativeMemoryTracking=summary"; [ "$NETTY_FLAG" = 1 ] && EXTRA="-Dio.netty.maxDirectMemory=0 $EXTRA"
cd "$CL" || die "no clone"
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
log "+ CASSANDRA_LOG_DIR=$OUT/logs MAX_HEAP_SIZE=8G JVM_EXTRA_OPTS=\"$EXTRA\" bin/cassandra -p $OUT/cassandra.pid"
T0=$(date +%s)
CASSANDRA_LOG_DIR="$OUT/logs" MAX_HEAP_SIZE=8G JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p "$OUT/cassandra.pid" > "$OUT/cassandra.out" 2>&1
up=0
for i in $(seq 1 180); do
  sleep 5
  [ -n "$(node_pids)" ] || die "daemon died during start (see $OUT/logs/system.log)"
  if bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$(bin/nodetool statusbinary 2>/dev/null)" = running ]; then up=1; break; fi
done
[ $up = 1 ] || die "node not UN + binary running within 900 s"
PID=$(node_pids); log "node up after $(( $(date +%s) - T0 )) s, pid $PID"
run bin/nodetool status
tr '\0' '\n' < /proc/$PID/cmdline | grep -E 'maxDirectMemory|NativeMemoryTracking|Xmx|Xms|UseG1GC|MaxDirectMemorySize' | sed 's/^/jvm-arg: /'
run bin/nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytes
run bin/nodetool sjk mx -b org.apache.cassandra.db:type=StorageService -mg -f NativeTransportMaxConcurrentRequestsInBytesPerIp
grep -E 'commitlog_sync|group window|native_transport_max_request|write_request_timeout|native_transport_timeout' "$OUT/logs/system.log" | head -5

# step 4: schema, settle, idle baseline
run python3 "$TOOLS/v4load.py" 127.0.0.1 9042 1 1 1 0 setup || die "schema setup failed"
run sleep 15
log "+ java -cp $TOOLS InflightProbe 127.0.0.1 7199 200 10000 > $OUT/base.csv"
java -cp "$TOOLS" InflightProbe 127.0.0.1 7199 200 10000 > "$OUT/base.csv" || die "baseline probe failed"
log "baseline rows: $(($(wc -l < "$OUT/base.csv") - 1))"
( echo "t=$(date +%s%3N) baseline"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other' ) > "$OUT/nmt-base.txt" 2>&1; cat "$OUT/nmt-base.txt"

# step 5: probe + NMT loop
java -cp "$TOOLS" InflightProbe 127.0.0.1 7199 200 "$PROBE_MS" > "$OUT/run.csv" & PROBE_PID=$!
PROBE_T0=$(date +%s%3N); log "probe started pid $PROBE_PID at $PROBE_T0"
( while sleep 1; do echo "t=$(date +%s%3N)"; jcmd "$PID" VM.native_memory summary | grep -A1 '^-  *Other'; done ) > "$OUT/nmt.txt" 2>&1 & NMT_PID=$!
sleep 1

# step 6: workload
CT0=$(date +%s%3N); log "client start $CT0"
python3 "$TOOLS/v4load.py" 127.0.0.1 9042 "$C" "$NREQ" "$BLOB" "$T" | tee "$OUT/client.txt"
CT1=$(date +%s%3N); log "client end $CT1 (elapsed $(( CT1 - CT0 )) ms; probe offset start $(( CT0 - PROBE_T0 )) ms, end $(( CT1 - PROBE_T0 )) ms)"
echo "client_start_ms=$CT0 client_end_ms=$CT1 probe_start_ms=$PROBE_T0" > "$OUT/times.txt"

# step 7: wait for the probe, stop NMT
log "waiting for probe"; wait $PROBE_PID; log "probe exit $?"; PROBE_PID=
kill $NMT_PID 2>/dev/null; NMT_PID=
run bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -mg -f Value
grep -cE '^(ERROR|WARN)' "$OUT/logs/system.log" | sed 's/^/system.log ERROR+WARN lines: /'
grep -E '^ERROR' "$OUT/logs/system.log" | head -5
grep -c 'LEAK:' "$OUT/logs/system.log" | sed 's/^/netty LEAK lines: /'

# step 8: stop the node (trap does it too)
stop_node
# step 9: reduce
log "+ python3 $TOOLS/reduce.py $OUT"
python3 "$TOOLS/reduce.py" "$OUT" | tee "$OUT/summary.txt"
