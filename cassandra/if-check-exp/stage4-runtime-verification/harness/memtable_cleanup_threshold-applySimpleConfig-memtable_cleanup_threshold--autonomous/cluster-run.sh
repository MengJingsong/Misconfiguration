#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-24) of memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous, one run.
# usage: cluster-run.sh <label> <memtable_cleanup_threshold> <memtable_heap_space e.g. 256MiB> <mode: both | p2only | startfail>
#   both      = phase 1 (moderate, fixed 5000/s) then, 10 s later, phase 2 (heavy, threads=128)   (B3c/B3e)
#   p2only    = phase 2 only (the C4 positive control, B3h amended)
#   startfail = start with an invalid value; wait up to 120 s for the daemon to exit (B3e amended)
# Env: C (clone, default $W/cassandra-run8), OUT (log root, default .../cluster), N1/N2 (partitions per phase, default 2000000).
# Node data under $W/node-mct (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; TH=$2; HS=$3; MODE=$4
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run8}; N=$W/node-mct
OUT=${OUT:-$W/logs/memtable_cleanup_threshold-applySimpleConfig/cluster}; N1=${N1:-2000000}; N2=${N2:-2000000}
L=$OUT/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
x() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local r=$?; log "rc=$r"; return $r; }
mark() { echo "$1 $(python3 -c 'import time;print(int(time.time()*1000))') $(wc -c < "$N/logs/system.log" | tr -d ' ')" >> "$L/markers.txt"; }
ps -eo command | grep -q '[C]assandraDaemon' && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
pgrep -f cassandra-stress >/dev/null && { log "ABORT: a cassandra-stress is running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
log "run $LABEL memtable_cleanup_threshold=$TH memtable_heap_space=$HS mode=$MODE N1=$N1 N2=$N2 clone=$(git -C "$C" rev-parse HEAD)"
df -h "$W" | tail -1 >> "$L/commands.log"
mkdir -p "$W/harness-bin-mct"; x javac -d "$W/harness-bin-mct" "$H/Sampler.java" || exit 1
# node directories and configuration (B3a)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(memtable_allocation_type|memtable_heap_space|memtable_offheap_space|memtable_flush_writers|memtable_cleanup_threshold|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "memtable_allocation_type: heap_buffers"; echo "memtable_heap_space: $HS"
  echo "memtable_flush_writers: 2"; echo "memtable_cleanup_threshold: $TH"; } >> "$Y"
tail -12 "$Y" > "$L/yaml-overrides.txt"
# start the node
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
SPID=
stop_node() {
  log "stopping node"; touch "$L/stop"; [ -n "$SPID" ] && { wait "$SPID" 2>/dev/null; SPID=; }
  pkill -f cassandra-stress 2>/dev/null
  if kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool drain ) >> "$L/commands.log" 2>&1 & DRP=$!
    for i in $(seq 1 60); do kill -0 "$DRP" 2>/dev/null || break; sleep 1; done; kill "$DRP" 2>/dev/null; log "drain done or bounded"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f 'org.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  sleep 2; if ps -eo command | grep -q '[C]assandraDaemon'; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi
  pgrep -f cassandra-stress >/dev/null && log "WARNING: cassandra-stress still running" || log "no cassandra-stress left"; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
  du -sh "$N/data" "$N/commitlog" >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
if [ "$MODE" = startfail ]; then
  res=timeout
  for i in $(seq 1 60); do
    kill -0 "$NPID" 2>/dev/null || { res=exited; break; }
    if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1'); then res=started; break; fi
    sleep 2
  done
  rc=na; [ "$res" = exited ] && { wait "$NPID" 2>/dev/null; rc=$?; }
  log "startfail result: $res (launcher rc=$rc if exited) after ~$((i*2)) s"
  { echo "result $res"; grep -h 'memtable_cleanup_threshold' "$L/node.out" "$N/logs/system.log" 2>/dev/null | grep -v 'Node configuration' | cut -c1-400 | head -10; } > "$L/startfail.txt"
  cat "$L/startfail.txt" >> "$L/commands.log"
  trap - EXIT; stop_node; finish
  python3 -I "$H/summarize.py" "$L" "$TH" | tee "$L/summary.txt"
  exit 0
fi
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
log "node UN, statusbinary running; daemon pid $(pgrep -f 'org.apache.cassandra.service.CassandraDaemon' | head -1)"
# C1 read-back (B3d (4), B3h C1)
grep -m1 'Node configuration:\[' "$N/logs/system.log" | tr ';' '\n' | grep -E '^ *(memtable_cleanup_threshold|memtable_heap_space|memtable_flush_writers|memtable_allocation_type|commitlog_total_space)=' > "$L/config-readback.txt"
grep -E 'memtable_cleanup_threshold has been deprecated|memtable_cleanup_threshold is set very low|Global memtable on-heap threshold' "$N/logs/system.log" | head -5 >> "$L/config-readback.txt"
cat "$L/config-readback.txt" >> "$L/commands.log"
java -cp "$W/harness-bin-mct" Sampler 7199 "$L/samples.csv" "$L/stop" > "$L/sampler.err" 2>&1 & SPID=$!
log "sampler pid $SPID"; sleep 3
STRESS=(tools/bin/cassandra-stress write cl=ONE -col "n=FIXED(5)" "size=FIXED(200)")
if [ "$MODE" = both ]; then
  mark p1start
  log "+ ${STRESS[*]} n=$N1 -rate threads=8 fixed=5000/s -schema replication(factor=1)"
  s0=$(date +%s); (cd "$C" && "${STRESS[@]:0:2}" n=$N1 "${STRESS[@]:2}" -rate threads=8 fixed=5000/s -schema "replication(factor=1)") > "$L/stress-p1.log" 2>&1
  log "phase 1 stress rc=$? after $(( $(date +%s) - s0 )) s"; mark p1end
  sleep 10
fi
mark p2start
log "+ ${STRESS[*]} n=$N2 -rate threads=128 -schema replication(factor=1)"
s0=$(date +%s); (cd "$C" && "${STRESS[@]:0:2}" n=$N2 "${STRESS[@]:2}" -rate threads=128 -schema "replication(factor=1)") > "$L/stress-p2.log" 2>&1
log "phase 2 stress rc=$? after $(( $(date +%s) - s0 )) s"; mark p2end
sleep 10; mark p2cut
(cd "$C" && bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation" -mg -f Count) > "$L/sjk-blocked-end.txt" 2>&1
touch "$L/stop"; wait "$SPID" 2>/dev/null; SPID=
# phase excerpts by byte offset (B3d (3))
off() { awk -v k="$1" '$1==k{print $3}' "$L/markers.txt"; }
cut_log() { local a=$1 b=$2; tail -c +$((a+1)) "$N/logs/system.log" | head -c $((b-a)); }
[ "$MODE" = both ] && cut_log "$(off p1start)" "$(off p2start)" | grep -E 'Flushing largest|Enqueuing flush' > "$L/flush-lines-p1.txt"
cut_log "$(off p2start)" "$(off p2cut)" | grep -E 'Flushing largest|Enqueuing flush' > "$L/flush-lines-p2.txt"
grep -c 'java.lang.OutOfMemoryError' "$N/logs/system.log" > "$L/oom-count.txt"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v -i 'Small cdc volume\|jemalloc\|swap\|max map count' | head -200 > "$L/error-warn.txt"
trap - EXIT; stop_node; finish
python3 -I "$H/summarize.py" "$L" "$TH" | tee "$L/summary.txt"
