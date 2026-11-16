#!/usr/bin/env bash
# OOM-exp node smoke test (2026-11-16): can this aarch64 m400 node run Cassandra 5.0.9 with the
# native libraries the OOM cases depend on, under a cgroup v2 budget, and serve a short workload?
# Runs on the node itself. Leaves nothing running.
set -uo pipefail
C=/mydata/oom-smoke/cassandra-run1
D=/mydata/oom-smoke/run1
mkdir -p "$D"
LOG=$D/smoke.log
log()  { echo "[$(date +%s%3N) $(date +%T)] $*" | tee -a "$LOG"; }
SYSLOG=$C/logs/system.log

log "== inventory"
{ uname -a; java -version 2>&1; ant -version; lscpu | head -12; free -m; swapon --show; cat /proc/sys/vm/overcommit_memory;
  cat /sys/kernel/mm/transparent_hugepage/enabled; git -C "$C" describe --tags; } > "$D/inventory.txt" 2>&1

log "== preflight"
pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' && { log "FAIL: a CassandraDaemon is already running"; exit 1; }
ss -ltn | grep -E ':(7000|7199|9042)\b' && { log "FAIL: ports busy"; exit 1; }

cd "$C"
rm -rf data/* logs/*; mkdir -p logs
export MAX_HEAP_SIZE=2G
export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1024M"
UNIT="smoke-cass-$(date +%s)"
BUDGET=4096
log "+ systemd-run --user --scope -p MemoryMax=${BUDGET}M -p MemorySwapMax=0 --unit=$UNIT -- bin/cassandra -f  (heap 2G, direct 1024M)"
T0=$(date +%s)
systemd-run --user --scope -p MemoryMax=${BUDGET}M -p MemorySwapMax=0 --unit="$UNIT" -- bin/cassandra -f > "$D/stdout.txt" 2>&1 &
SCOPE_PID=$!
unset MAX_HEAP_SIZE JVM_EXTRA_OPTS
ok=0
for i in $(seq 1 600); do
  if grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; then ok=1; break; fi
  kill -0 $SCOPE_PID 2>/dev/null || { log "FAIL: node died during start"; break; }
  sleep 1
done
log "startup ok=$ok in $(( $(date +%s) - T0 )) s"
PID=$(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' | head -1)
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup 2>/dev/null)
log "pid=$PID cgroup=$CG memory.max=$(cat $CG/memory.max 2>/dev/null) swap.max=$(cat $CG/memory.swap.max 2>/dev/null)"
ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
log "jvm: $(grep -E '^-Xm[sx]|MaxDirectMemorySize|UseG1GC|UseConcMarkSweepGC|UseParallelGC|UseZGC|UseShenandoah' $D/jvm-args.txt | tr '\n' ' ')"

log "== native libraries and platform warnings (system.log)"
grep -E 'Netty using|epoll not available|JNA|mlockall|lz4-java|Native|native librar|Unable to|unsupported|architecture|aarch|arm' "$SYSLOG" \
  | grep -v 'Native protocol supported versions' | cut -c1-300 | tee "$D/native-lines.txt" | tee -a "$LOG"
log "WARN lines: $(grep -c '^WARN' $SYSLOG)  ERROR lines: $(grep -c '^ERROR' $SYSLOG)"
grep -E '^(WARN|ERROR)' "$SYSLOG" | cut -c1-300 > "$D/warn-error.txt"

if [ $ok = 1 ]; then
  log "== nodetool"
  bin/nodetool status 2>&1 | tail -3 | tee -a "$LOG"
  log "statusbinary: $(bin/nodetool statusbinary 2>&1)"
  log "== stress write"
  T=$(date +%s)
  tools/bin/cassandra-stress write n=200000 cl=ONE -rate threads=32 -log file=$D/stress-write.log > /dev/null 2>&1
  log "write exit=$? secs=$(( $(date +%s)-T ))"
  grep -E '^(Op rate|Partition rate|Latency mean|Latency 99th|Total partitions|Total errors|Total operation time)' $D/stress-write.log | tee -a "$LOG"
  log "== stress read"
  T=$(date +%s)
  tools/bin/cassandra-stress read n=100000 cl=ONE -rate threads=32 -log file=$D/stress-read.log > /dev/null 2>&1
  log "read exit=$? secs=$(( $(date +%s)-T ))"
  grep -E '^(Op rate|Partition rate|Latency mean|Latency 99th|Total partitions|Total errors|Total operation time)' $D/stress-read.log | tee -a "$LOG"
  log "== memory after workload"
  bin/nodetool info 2>&1 | grep -E 'Heap Memory|Off Heap' | tee -a "$LOG"
  log "cgroup memory.peak=$(cat $CG/memory.peak 2>/dev/null) current=$(cat $CG/memory.current) events: $(tr '\n' ' ' < $CG/memory.events)"
  jcmd $PID GC.heap_info > "$D/gc-heap-info.txt" 2>&1
  jcmd $PID VM.flags > "$D/vm-flags.txt" 2>&1
  jcmd $PID Thread.print > "$D/threads.txt" 2>&1
  log "threads in epollWait: $(grep -c 'io.netty.channel.epoll.Native.epollWait' $D/threads.txt)  in NIO select: $(grep -c 'sun.nio.ch.EPoll.wait\|SelectorImpl.select' $D/threads.txt)"
fi

log "== stop"
kill $PID 2>/dev/null
for i in $(seq 1 60); do pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null || break; sleep 1; done
pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' && { kill -9 $PID; sleep 2; }
wait $SCOPE_PID 2>/dev/null
log "left running: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') stress=$(pgrep -fc '[o]rg.apache.cassandra.stress') scope=$(systemctl --user list-units --no-legend "$UNIT.scope" | wc -l)"
cp "$SYSLOG" "$D/system.log" 2>/dev/null; cp "$C/logs/gc.log"* "$D/" 2>/dev/null
log "done"
