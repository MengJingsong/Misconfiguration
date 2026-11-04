#!/usr/bin/env bash
# Unit tier (case B2, amended 2026-10-26): compile GlobalInFlightLimitProbe against the tree's build/classes/main and run
# one fresh JVM per mode. usage: bash unit-run.sh [instrument]   (logs to ~/s4-b8-cr-logs/unit/)
# "instrument" = known-answer check of the probe itself (a mutant limiter that does not enforce) -- see below.
set -uo pipefail
CL=$HOME/s4-b8-cr; H=$HOME/s4-b8-cr-harness; OUT=$HOME/s4-b8-cr-logs/unit; W=$HOME/s4-b8-cr-unitwork
mkdir -p "$OUT" "$W/classes"
exec > >(tee -a "$OUT/unit-run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
log "START unit tier ($*)"; git -C "$CL" describe --tags; sha256sum "$H/GlobalInFlightLimitProbe.java"
CP="$CL/build/classes/main:$CL/build/lib/jars/*:$CL/lib/*"
javac -cp "$CP" -d "$W/classes" "$H/GlobalInFlightLimitProbe.java" || { log "FAIL compile"; exit 1; }
OPTS=$(grep -v '^#' "$CL/conf/jvm11-clients.options" | grep -v '^$' | tr '\n' ' ')
mkyaml() {   # $1 = file, rest = extra lines
  local f=$1; shift
  { echo "cluster_name: s4cr-unit"; echo "partitioner: org.apache.cassandra.dht.Murmur3Partitioner"; echo "commitlog_sync: periodic"
    echo "commitlog_sync_period: 10s"; echo "commitlog_segment_size: 5MiB"; echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "endpoint_snitch: SimpleSnitch"; echo "seed_provider:"; echo "  - class_name: org.apache.cassandra.locator.SimpleSeedProvider"
    echo "    parameters:"; echo "      - seeds: \"127.0.0.1:7000\""
    echo "data_file_directories: [$W/data]"; echo "commitlog_directory: $W/commitlog"; echo "hints_directory: $W/hints"
    echo "saved_caches_directory: $W/saved"; echo "cdc_raw_directory: $W/cdc"
    for l in "$@"; do echo "$l"; done; } > "$f"
}
mkyaml "$W/plain.yaml"; mkyaml "$W/explicit.yaml" "native_transport_max_message_size: 1MiB"
runmode() {  # label yaml mode [L]
  local lab=$1 y=$2; shift 2
  log "+ java -Xmx512m ... GlobalInFlightLimitProbe $*  (yaml $y)"
  java -Xmx512m $OPTS -Dcassandra.config=file://$y -Dcassandra.storagedir=$W/storage -Dcassandra.logdir=$W/logs \
       -cp "$W/classes:$CP" org.apache.cassandra.transport.GlobalInFlightLimitProbe "$@" > "$OUT/$lab.out" 2> "$OUT/$lab.err"
  local rc=$?; log "exit $rc ($lab)"; grep -E '^(CHECK|U,|RESULT)' "$OUT/$lab.out"; [ -s "$OUT/$lab.err" ] && { echo "--- stderr tail"; tail -5 "$OUT/$lab.err"; }
}
if [ "${1:-}" = instrument ]; then
  # known-answer instrument check: (1) a sweep with a deliberately wrong expectation (-Dprobe.mutant) must report MISMATCH and exit 1;
  # (2) the v4 mode must detect usage > L (its "usage_gt_L" check is true only when the forced allocate pushed usage past L).
  log "+ mutant sweep (expect MISMATCH on successes)"
  java -Xmx512m $OPTS -Dprobe.mutant=1 -Dcassandra.config=file://$W/plain.yaml -Dcassandra.storagedir=$W/storage -Dcassandra.logdir=$W/logs \
       -cp "$W/classes:$CP" org.apache.cassandra.transport.GlobalInFlightLimitProbe sweep 8388608 > "$OUT/ki-mutant.out" 2>&1; log "mutant exit $? (expected 1)"
  grep -E 'successes |RESULT' "$OUT/ki-mutant.out"
  runmode ki-v4 "$W/plain.yaml" v4 | grep -E 'usage_gt_L|RESULT'
  log "END instrument"; exit 0
fi
runmode sweep-1MiB "$W/plain.yaml" sweep 1048576
runmode sweep-8MiB "$W/plain.yaml" sweep 8388608
runmode sweep-64MiB "$W/plain.yaml" sweep 67108864
runmode default "$W/plain.yaml" default
runmode control-1GiB "$W/plain.yaml" control 1073741824
runmode v4-8MiB "$W/plain.yaml" v4
runmode msg-default "$W/plain.yaml" msg-default
runmode msg-explicit "$W/explicit.yaml" msg-explicit
log "SUMMARY"; grep -h '^RESULT' "$OUT"/*.out | tee "$OUT/summary.txt"
log "END unit tier"
