#!/usr/bin/env bash
# Cluster tier (B3e as amended by M4-M6, M8) of commitlog_max_compression_buffers_in_pool-...-usedbuffers--autonomous.
# usage: bash cluster-run.sh <run-name> <cfg>      cfg: N3 N6 N12 C1 C2 N1   (on apt138)
# Node tree /mydata/jingsong-cass-s4/o45/node (copy of the built src tree, JMX_PORT 7499); data /mydata/jingsong-cass-s4/o45/data.
# Output /mydata/jingsong-cass-s4/o45/<run>/<cfg>/: session.log (every command), events.txt (epoch ms marks),
# samples.csv (O45Jmx, 1 s), ctx.csv (RSS, commitlog files, 10 s), jstack/<ms>.txt (10 s), stress.out, logs/ (system.log, gc).
# Stops the node and every helper it started on any exit.
set -uo pipefail
RUN=${1:?run}; CFG=${2:?cfg}
B=/mydata/jingsong-cass-s4/o45; H=$B/harness; NODE=$B/node; DATA=$B/data; O=$B/$RUN/$CFG
mkdir -p "$O/jstack" "$O/logs"; LOG=$O/session.log; : > "$LOG"; EV=$O/events.txt; : > "$EV"
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
mark() { echo "$1 $(date +%s%3N)" >> "$EV"; say "mark $1"; }
run() { say "+ $*"; "$@" >> "$LOG" 2>&1; local rc=$?; say "  rc=$rc"; return $rc; }
NT() { "$NODE/bin/nodetool" -h 127.0.0.1 -p 7499 "$@"; }
PIDS=()
cleanup() {
  for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done
  if [ -s "$O/cass.pid" ]; then
    CP=$(cat "$O/cass.pid")
    if kill -0 "$CP" 2>/dev/null; then
      say "cleanup: drain + stop node $CP"
      timeout 900 "$NODE/bin/nodetool" -h 127.0.0.1 -p 7499 drain >> "$LOG" 2>&1; say "  drain rc=$?"
      kill "$CP" 2>/dev/null
      for i in $(seq 1 300); do kill -0 "$CP" 2>/dev/null || break; sleep 1; done
      kill -0 "$CP" 2>/dev/null && { say "cleanup: node still alive after 300 s, kill -9"; kill -9 "$CP"; }
    fi
  fi
  pkill -P $$ 2>/dev/null
  say "cleanup: CassandraDaemon processes of this tree left: $(ps -eo args | grep '[C]assandraDaemon' | grep -c "$NODE")"
  mark end
}
trap cleanup EXIT
say "cluster-run $RUN $CFG host $(hostname -s); harness md5 $(cd "$H" && md5sum cluster-run.sh patch_yaml.py O45Jmx.java | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h /mydata | tail -1)"; say "free: $(free -m | awk '/Mem:/{print "total "$2" MiB, available "$7" MiB"}')"
for p in 7300 7301 7499 9342; do ss -ltn | grep -q ":$p\b" && { say "port $p busy: stop"; exit 2; }; done
[ "$(ps -eo args | grep '[C]assandraDaemon' | grep -c "$NODE")" = 0 ] || { say "a node of this tree is running: stop"; exit 2; }
run rm -rf "$DATA"; mkdir -p "$DATA"
run python3 "$H/patch_yaml.py" "$NODE/conf/cassandra.yaml.orig" "$NODE/conf/cassandra.yaml" "$CFG" "$DATA"
cp "$NODE/conf/cassandra.yaml" "$O/cassandra.yaml"
ulimit -n 100000 2>/dev/null; say "ulimit -n $(ulimit -n)"
mark start_node
say "+ MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M MAX_DIRECT_MEMORY_SIZE=4G CASSANDRA_LOG_DIR=$O/logs bin/cassandra -p $O/cass.pid"
( cd "$NODE" && MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M MAX_DIRECT_MEMORY_SIZE=4G CASSANDRA_LOG_DIR=$O/logs bin/cassandra -p "$O/cass.pid" > "$O/logs/startup.out" 2>&1 < /dev/null )
for i in $(seq 1 60); do [ -s "$O/cass.pid" ] && break; sleep 1; done
CP=$(cat "$O/cass.pid" 2>/dev/null); say "node pid $CP"
UP=0
for i in $(seq 1 120); do
  kill -0 "$CP" 2>/dev/null || { say "node died during start"; break; }
  if NT status 2>/dev/null | grep -q '^UN' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then UP=1; break; fi
  sleep 2
done
mark node_up_or_failed
say "node up=$UP; JVM flags: $(tr '\0' ' ' < /proc/$CP/cmdline 2>/dev/null | grep -o -- '-Xm[sxn][^ ]*\|-XX:MaxDirectMemorySize=[^ ]*' | tr '\n' ' ')"
grep -h -m3 'commitlog_max_compression_buffers_in_pool\|IllegalArgumentException' "$O/logs/system.log" 2>/dev/null | cut -c1-400 >> "$LOG"
if [ "$CFG" = N1 ]; then
  say "N1: start-up check only. up=$UP; IllegalArgumentException lines in system.log: $(grep -c IllegalArgumentException "$O/logs/system.log" 2>/dev/null)"
  grep -h -B2 -A12 'IllegalArgumentException' "$O/logs/system.log" "$O/logs/startup.out" 2>/dev/null | head -60 > "$O/n1-excerpt.txt"
  exit 0
fi
[ "$UP" = 1 ] || { say "node did not come up: stop"; exit 3; }
java -cp "$B/harness-classes" O45Jmx 7499 1000 > "$O/samples.csv" 2> "$O/poller.err" & PIDS+=($!)
( while true; do t=$(date +%s%3N); echo "$t,$(ps -o rss= -p "$CP" | tr -d ' '),$(grep -m1 RssAnon /proc/$CP/status | awk '{print $2}'),$(ls "$DATA/commitlog" | wc -l),$(du -sm "$DATA/commitlog" | cut -f1)" >> "$O/ctx.csv"; sleep 10; done ) & PIDS+=($!)
mark idle_start
sleep 30
mark idle_end
( while true; do t=$(date +%s%3N); jstack "$CP" > "$O/jstack/$t.txt" 2>&1; sleep 10; done ) & JS=$!; PIDS+=($JS)
mark stress_start
say "+ cassandra-stress write duration=${DUR:-240s} no-warmup cl=ONE -col n=FIXED(8) size=FIXED(1024) -rate threads=64 -node 127.0.0.1 -port native=9342 jmx=7499 -mode native cql3 -errors ignore -log file=$O/stress.log"
( cd "$NODE" && tools/bin/cassandra-stress write duration=${DUR:-240s} no-warmup cl=ONE -col 'n=FIXED(8)' 'size=FIXED(1024)' -rate threads=64 -node 127.0.0.1 -port native=9342 jmx=7499 -mode native cql3 -errors ignore -log file="$O/stress.log" > "$O/stress.out" 2>&1 < /dev/null )
say "  stress rc=$?"
mark stress_end
sleep 30
mark post_end
kill "$JS" 2>/dev/null
NT tpstats > "$O/tpstats.txt" 2>&1
grep -E '^(Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time)' "$O/stress.out" >> "$LOG"
say "done; ERROR lines in system.log: $(grep -c '^ERROR' "$O/logs/system.log")"
