#!/usr/bin/env bash
# usage: cluster-run.sh <label> <N|unset> <cqllog on|off> <threshold TRACE|DEBUG|WARN> [steps="2000 10000 20000 40000 100000"]
#   (case B3e, as amended 2026-10-27).  One arm: fresh dirs, one node with -Dcassandra.virtual.logs.max.rows=N (or none),
#   the private logback.xml of make-node.sh, org.apache.cassandra raised to TRACE only for the workload, cumulative stress
#   write steps (cassandra-stress write n=<step ops> threads=32), after each step: debug.log event count, row listing of
#   system_views.system_logs, a collecting class histogram.  Output: $OUT/<label>/.
set -uo pipefail
label=$1; N=$2; cql=$3; lvl=$4; steps=${5:-"2000 10000 20000 40000 100000"}
HARN=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/c4-vlr}; T=$HOME/stage4-vlr/node; export T; OUT=${OUT:-$HOME/stage4-logs/vlr/run1/cluster}/$label
mkdir -p "$OUT"; cd "$C"; ulimit -n 100000
exec > >(tee -a "$OUT/cmdlog.txt") 2>&1
ts() { date +%s%3N; }
daemons() { ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | wc -l; }   # java processes whose arguments name CassandraDaemon
events() { grep -cE '^(TRACE|DEBUG|INFO|WARN|ERROR) ' $T/logs/debug.log; }
echo "== $label N=$N cqllog=$cql threshold=$lvl steps=[$steps] start $(ts)"
echo "CassandraDaemon processes before: $(daemons)"
rm -rf "$T"; "$HARN/make-node.sh" "$cql" "$lvl" > "$OUT/make-node.txt"; cat "$T/logback.diff" > "$OUT/logback.diff"
EXTRA=""; [ "$N" != unset ] && EXTRA="-Dcassandra.virtual.logs.max.rows=$N"
echo "JVM_EXTRA_OPTS=$EXTRA MAX_HEAP_SIZE=2G"; echo "$EXTRA" > "$OUT/jvm-extra.txt"
CASSANDRA_CONF=$T/conf CASSANDRA_LOG_DIR=$T/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M JVM_EXTRA_OPTS="$EXTRA" bin/cassandra -p $T/cassandra.pid > $T/stdout.txt 2>&1
for i in $(seq 1 120); do
  s=$(bin/nodetool statusbinary 2>/dev/null | tr -d '\n'); [ "$s" = running ] && break
  pgrep -F $T/cassandra.pid >/dev/null 2>&1 || { echo "daemon died at start"; tail -30 $T/stdout.txt; exit 1; }; sleep 3
done
echo "node up $(ts): $(bin/nodetool statusbinary)"
PID=$(cat $T/cassandra.pid); echo "pid $PID"
jcmd $PID VM.flags | tr ' ' '\n' | grep -E "MaxHeapSize" | tee "$OUT/vmflags.txt"
tr '\0' '\n' < /proc/$PID/cmdline | grep -E "virtual.logs|Xmx" | tee "$OUT/proc-args.txt"
grep -h "capacity of virtual table" $T/logs/debug.log | tee "$OUT/capacity-line.txt"
sleep 10
snap() {  # snap <tag>
  local tag=$1
  sleep 10
  echo "events_debuglog=$(events)" > "$OUT/$tag.events"; echo "snapshot_epoch_ms=$(date +%s%3N)" >> "$OUT/$tag.events"
  jcmd $PID GC.class_histogram > "$OUT/hist-$tag.txt" 2>&1
  jcmd $PID GC.heap_info > "$OUT/heap-$tag.txt" 2>&1
  # rows as the client sees them: paging off, one line per (timestamp, order_in_millisecond); newest first (reversed clustering)
  bin/cqlsh --request-timeout=600 127.0.0.1 -e "paging off; select timestamp, order_in_millisecond from system_views.system_logs" > "$OUT/rows-$tag.txt" 2>&1
  grep -E '^ 20' "$OUT/rows-$tag.txt" | awk -F'|' '{print $1}' | sed -n '1p;$p' > "$OUT/newest-oldest-$tag.txt"
  grep -E '^ 20' "$OUT/rows-$tag.txt" | wc -l > "$OUT/cqlrows-$tag.txt"; rm -f "$OUT/rows-$tag.txt"
  echo "snap $tag: events=$(events) cqlrows=$(cat $OUT/cqlrows-$tag.txt) logMessageInstances=$(grep 'LogMessagesTable\$LogMessage' $OUT/hist-$tag.txt | awk '{print $2}') $(date +%s%3N)"
}
snap base
bin/nodetool setlogginglevel org.apache.cassandra TRACE
done_ops=0
for st in $steps; do
  add=$((st - done_ops)); done_ops=$st
  echo "step: +$add ops (cumulative $st) $(ts)"
  tools/bin/cassandra-stress write n=$add -rate threads=32 -node 127.0.0.1 > "$OUT/stress-$st.txt" 2>&1
  grep -E "Op rate|Total errors" "$OUT/stress-$st.txt"
  bin/nodetool setlogginglevel org.apache.cassandra DEBUG
  snap "s$st"
  bin/nodetool setlogginglevel org.apache.cassandra TRACE
done
bin/nodetool setlogginglevel org.apache.cassandra DEBUG
bin/cqlsh --request-timeout=600 127.0.0.1 -e "select timestamp, order_in_millisecond, level, logger, message from system_views.system_logs limit 3" > "$OUT/newest3.txt" 2>&1
sleep 5; cp $T/logs/debug.log "$OUT/debug.log"; cp $T/logs/system.log "$OUT/system.log"
bin/nodetool stopdaemon > /dev/null 2>&1
for i in $(seq 1 60); do pgrep -F $T/cassandra.pid >/dev/null 2>&1 || break; sleep 2; done
sleep 2; echo "CassandraDaemon processes left: $(daemons)"
rm -rf "$T"; echo "== $label end $(ts)"
