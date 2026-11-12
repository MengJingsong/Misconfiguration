#!/usr/bin/env bash
# Cluster tier (B3, with AM2-AM4) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous.
# usage: bash cluster-run.sh <run-name> [F values...]   (default F: 32 96 288 2080)
# One node from /mydata/jingsong-cass-s4/o06/src on 127.0.0.1 (storage 7400/7401, native 9442, JMX 7599).
# Loads once (F=32), then per F: restart with file_cache_size=F, baseline, 5 s samplers, stress read, 60 s tail.
# Every command and its output is logged to session.txt. Stops at the first failed check. Stops the node at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=/mydata/jingsong-cass-s4/o06/src; B=/mydata/jingsong-cass-s4/o06
RUN=${1:-run1}; shift || true; FS=${*:-32 96 288 2080}
L=$B/logs/$RUN/cluster; NODE=$B/node; CONF=$B/conf-run; mkdir -p "$L"
LOG=$L/session.txt
export CASSANDRA_CONF=$CONF CASSANDRA_LOG_DIR=$L/cass-logs
mkdir -p "$CASSANDRA_LOG_DIR"
ulimit -n 100000 2>/dev/null || ulimit -n $(ulimit -Hn)
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
run() { say "+ $*"; "$@" >> "$LOG" 2>&1; local rc=$?; say "  rc=$rc"; return $rc; }
die() { say "FATAL: $*"; stop_node; exit 1; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7599 "$@"; }
CQ() { "$C/bin/cqlsh" 127.0.0.1 9442 -e "$1"; }
PIDF=$NODE/pid
nodepid() { [ -f "$PIDF" ] && cat "$PIDF"; }
alive() { local p; p=$(nodepid); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && tr '\0' ' ' < /proc/$p/cmdline | grep -q "CassandraDaemon" ; }
stop_node() {
  if alive; then local p; p=$(nodepid); say "stopping node pid $p"; kill "$p"
    for i in $(seq 1 120); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    if kill -0 "$p" 2>/dev/null; then say "node pid $p did not exit in 120 s: kill -9"; kill -9 "$p"; sleep 2; fi
    say "node pid $p stopped"; fi
}
start_node() {
  local F=$1
  run python3 -I "$H/mkconf.py" "$C/conf" "$CONF" "$NODE" "$F" || die "mkconf"
  grep -E '^(file_cache_size|file_cache_enabled|key_cache_size|disk_access_mode|storage_port|native_transport_port):' "$CONF/cassandra.yaml" >> "$LOG"
  for p in 7400 7401 7599 9442; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && die "port $p busy"; done
  rm -f "$PIDF"
  say "+ bin/cassandra -p $PIDF (F=$F)"
  "$C/bin/cassandra" -p "$PIDF" > "$L/start-$F.out" 2>&1 < /dev/null
  for i in $(seq 1 60); do [ -s "$PIDF" ] && break; sleep 1; done
  [ -s "$PIDF" ] || die "no pid file"
  say "node pid $(nodepid) cwd $(readlink /proc/$(nodepid)/cwd)"
  for i in $(seq 1 240); do
    alive || die "daemon died during start"
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then say "UN and binary running after ${i}x2 s"; return 0; fi
    sleep 2
  done
  die "node not up in 480 s"
}
sample_once() { # $1 = tag file prefix
  java "$H/CcJmx.java" 7599 once "$L/jmx-$1.csv" >> "$LOG" 2>&1
  echo "$(date +%s%3N) $(CQ "SELECT name, capacity_bytes, size_bytes, entry_count FROM system_views.caches WHERE name='chunks';" 2>&1 | tr '\n' ' ')" >> "$L/cql-$1.txt"
  echo "$(date +%s%3N),$(jcmd "$(nodepid)" VM.native_memory summary 2>/dev/null | grep -A1 -E '^-\s+Other' | tr -s ' \n' ' '),rss_kb=$(ps -o rss= -p "$(nodepid)" | tr -d ' ')" >> "$L/nmt-$1.csv"
}
samplers_start() { # $1 = F
  local F=$1; STOP=$L/stop-$F; rm -f "$STOP"
  ( java "$H/CcJmx.java" 7599 poll "$L/jmx-$F.csv" 5000 "$STOP" >> "$L/sampler-jmx-$F.log" 2>&1 ) &
  SJ=$!
  ( while [ ! -e "$STOP" ]; do t=$(date +%s); echo "$(date +%s%3N) $(CQ "SELECT name, capacity_bytes, size_bytes, entry_count FROM system_views.caches WHERE name='chunks';" 2>&1 | tr '\n' ' ')" >> "$L/cql-$F.txt"; s=$((5 - $(date +%s) + t)); [ $s -gt 0 ] && sleep $s; done ) &
  SC=$!
  ( while [ ! -e "$STOP" ]; do t=$(date +%s); echo "$(date +%s%3N),$(jcmd "$(nodepid)" VM.native_memory summary 2>/dev/null | grep -A1 -E '^-\s+Other' | tr -s ' \n' ' '),rss_kb=$(ps -o rss= -p "$(nodepid)" | tr -d ' ')" >> "$L/nmt-$F.csv"; s=$((5 - $(date +%s) + t)); [ $s -gt 0 ] && sleep $s; done ) &
  SN=$!
  say "samplers pids $SJ $SC $SN"
}
samplers_stop() { touch "$STOP"; wait $SJ $SC $SN 2>/dev/null; say "samplers stopped"; }
mark() { echo "$(date +%s%3N) $*" >> "$L/marks.txt"; say "MARK $*"; }

say "cluster-run $RUN F=[$FS] host $(hostname -s) $(java -version 2>&1 | head -1) tree $(git -C $C describe --tags)"
say "harness md5 $(cd "$H" && md5sum cluster-run.sh mkconf.py CcJmx.java | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "free: $(free -g | awk '/Mem:/{print $7" GiB available"}'); df: $(df -h /mydata | tail -1)"
[ -d "$NODE/data/keyspace1" ] && die "node dir already holds data: refusing to reuse"
mkdir -p "$NODE"
# --- load (B3c, AM2), once, with F=32
start_node 32
mark load_start
"$C/tools/bin/cassandra-stress" write n=1500000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -schema 'replication(factor=1)' compression=LZ4Compressor -rate threads=32 -node 127.0.0.1 -port native=9442 jmx=7599 > "$L/stress-write.log" 2>&1 < /dev/null
say "stress write rc=$? $(grep -E 'Total partitions|Total errors|Op rate' "$L/stress-write.log" | tr -s ' ' | tr '\n' ';')"
mark load_end
run NT flush keyspace1 || die flush
run NT compact keyspace1 || die compact
run NT compactionstats
CQ "DESCRIBE TABLE keyspace1.standard1;" > "$L/describe.txt" 2>&1; cat "$L/describe.txt" >> "$LOG"
grep -q "'chunk_length_in_kb': '16'" "$L/describe.txt" && grep -q LZ4Compressor "$L/describe.txt" || die "table is not LZ4 16 KiB (AM2)"
NT tablestats keyspace1.standard1 > "$L/tablestats.txt" 2>&1; cat "$L/tablestats.txt" >> "$LOG"
ls -l "$NODE"/data/keyspace1/standard1-*/ >> "$LOG" 2>&1
for F in $FS; do
  stop_node
  start_node "$F"
  say "settle 30 s"; sleep 30
  run NT compactionstats
  mark "F=$F baseline"
  sample_once "$F-baseline"
  samplers_start "$F"
  sleep 6
  mark "F=$F read_start"
  "$C/tools/bin/cassandra-stress" read n=3000000 -col 'n=FIXED(1)' 'size=FIXED(1024)' -pop 'dist=UNIFORM(1..1500000)' -rate threads=32 -node 127.0.0.1 -port native=9442 jmx=7599 > "$L/stress-read-$F.log" 2>&1 < /dev/null
  say "stress read F=$F rc=$? $(grep -E 'Total partitions|Total errors|Op rate|Total operation time' "$L/stress-read-$F.log" | tr -s ' ' | tr '\n' ';')"
  mark "F=$F read_end"
  sleep 60
  mark "F=$F tail"
  samplers_stop
  NT info > "$L/info-$F.txt" 2>&1; grep -i "chunk cache" "$L/info-$F.txt" | tee -a "$LOG"
  say "pool-limit log lines so far: $(grep -c 'Maximum memory usage reached' "$CASSANDRA_LOG_DIR/system.log")"
  cp "$CASSANDRA_LOG_DIR/system.log" "$L/system-after-$F.log"
done
stop_node
say "leftover CassandraDaemon of this run: $(ps -eo pid,args | grep '[C]assandraDaemon' | grep -c "$B/")"
say "done"
