#!/usr/bin/env bash
# Cluster tier (B3 as amended 2026-10-27, C1-C5) of file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.
# usage: cluster-run.sh <run> <N> <read duration> <value> [<value> ...]
#   cluster-run.sh r1    8000000 10m 48MiB 96MiB 192MiB default 0MiB     run 1 (C4)
#   cluster-run.sh shake 400000  60s 48MiB 0MiB                          shakedown (not judged)
# One node on 127.0.0.1 from $W/cassandra-run63, MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M, JVM_EXTRA_OPTS = MaxDirectMemorySize=2G + NMT
# summary + Byteman agent with fcs-node.btm (observe-only; "BMFC ..." lines on node-<tag>.out). conf/data under $W/node-fcs (wiped at
# start and end). The STDOUT appender is removed from the node's logback.xml so node-<tag>.out carries the Byteman lines only.
# Sequence (C4): LOAD phase (default file_cache_size): start, stress write N, flush, compact, idle, stop. Then per value: conf with
# file_cache_size=<value> (key absent for "default"), start, Capacity/limit-line check, JMX sampler every 10 s, stress read for the
# duration, two quiet samples, NMT summary, greps, stop. Then stop, check, wipe.
# Node mechanics (tmo, nt, run, stop_node, final_check, start_node, wait_up, idle_wait) adapted from
# harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/cluster-run.sh (that file is not modified).
# Logs: $W/logs/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/cluster-<run>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
RUN=${1:?run}; N=${2:?N}; DUR=${3:?duration}; shift 3; VALUES=("$@")
H=$(cd "$(dirname "$0")" && pwd)
L=$W/logs/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/cluster-$RUN
rm -rf "$L"; mkdir -p "$L/node"; CL=$L/commands.log; S=$L/summary.txt; : > "$CL"; : > "$S"
C=$W/cassandra-run63; NODE=$W/node-fcs; BIN=$W/harness-bin-fcs
PID=""; SPID=""; OUT=""
XO="-XX:MaxDirectMemorySize=2G -XX:NativeMemoryTracking=summary -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/fcs-node.btm"
BASE=(file_cache_enabled=true concurrent_reads=32 disk_access_mode=standard memtable_allocation_type=heap_buffers)
now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { echo "[$(now)] $*" >> "$CL"; }
say() { echo "$*" >> "$S"; log "SUMMARY $*"; }
tmo() { perl -e '$t=shift; $p=fork; if(!$p){exec @ARGV; exit 127} $SIG{ALRM}=sub{kill 9,$p; waitpid $p,0; exit 124}; alarm $t; waitpid $p,0; exit($?>>8)' "$@"; }
nt()  { tmo 600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
ntl() { tmo 3600 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
run() { log "+ $*"; "$@" >> "$CL" 2>&1; local rc=$?; log "  exit=$rc"; return $rc; }
die() { say "ABORT: $*"; stop_sampler; stop_node; final_check; exit 1; }
stop_sampler() {
  [ -z "$SPID" ] && return 0
  touch "$L/.stop-sampler"; for i in $(seq 1 30); do kill -0 $SPID 2>/dev/null || break; sleep 1; done
  kill $SPID 2>/dev/null; SPID=""; rm -f "$L/.stop-sampler"
}
stop_node() {
  [ -z "$PID" ] && return 0
  kill -0 $PID 2>/dev/null || { PID=""; return 0; }
  run tmo 300 "$C/bin/nodetool" -h 127.0.0.1 -p 7199 drain
  kill $PID 2>/dev/null; for i in $(seq 1 90); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9 $PID"; kill -9 $PID; sleep 1; }
  PID=""; log "node stopped"
}
final_check() {
  local d; d=$(ps -eo command | grep "[C]assandra""Daemon"); say "final daemon processes: ${d:-none}"
  pgrep -f "[S]tress" >/dev/null && say "WARNING: a stress JVM is still running" || say "no stress JVM left"
  pgrep -f "[F]csSampler" >/dev/null && say "WARNING: a sampler is still running" || say "no sampler left"
  run rm -rf "$NODE"; say "node-fcs wiped: $([ -e "$NODE" ] && echo no || echo yes)"
}
start_node() {   # start_node <stdout file>
  OUT=$1
  log "+ start node CASSANDRA_CONF=$NODE/conf MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS=$XO > $OUT"
  CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$L/node MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$XO" nohup "$C/bin/cassandra" -f > "$OUT" 2>&1 < /dev/null &
  PID=$!; disown; log "pid $PID"
  wait_up
}
wait_up() {
  local t0; t0=$(date +%s)
  while :; do
    kill -0 $PID 2>/dev/null || die "node died during start"
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1 ' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then log "up after $(( $(date +%s) - t0 )) s"; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 600 ] && die "node not up in 600 s"
    sleep 3
  done
}
idle_wait() {   # no active compaction listed (pending-task estimate not used), then 5 s
  local t0; t0=$(date +%s)
  while :; do
    local cs a c
    cs=$(nt compactionstats 2>/dev/null); a=$(echo "$cs" | grep -c 'compaction type')
    c=$(nt tablestats keyspace1.standard1 2>/dev/null | awk -F': ' '/SSTable count/{print $2; exit}' | tr -d ' ')
    if [ "$a" = 0 ] && [ -n "$c" ]; then log "idle after $(( $(date +%s) - t0 )) s (active $a, sstables $c)"; sleep 5; return 0; fi
    [ $(( $(date +%s) - t0 )) -ge 3600 ] && { say "WARNING: not idle after 3600 s (active $a, sstables $c)"; return 1; }
    sleep 5
  done
}
conf() {   # conf <value>  (value "default" leaves file_cache_size unset)
  local extra=()
  [ "$1" != default ] && extra=("file_cache_size=$1")
  run "$H/make-node-conf.sh" "${BASE[@]}" ${extra[@]+"${extra[@]}"} || die "conf $1"
  sed -i '' 's#<appender-ref ref="STDOUT" */>##' "$NODE/conf/logback.xml"
  sed -n '/^# ---- stage4 fcs lines/,$p' "$NODE/conf/cassandra.yaml" > "$L/yaml-tail-$1.txt"
  say "CONF $1 yaml tail [$(tr '\n' ';' < "$L/yaml-tail-$1.txt")] logback STDOUT refs left: $(grep -c 'appender-ref ref="STDOUT"' "$NODE/conf/logback.xml")"
}
expected_cap() {   # bytes; default = min(512, maxMemory/4 MiB) MiB = 512 MiB for G1 -Xmx2G (DatabaseDescriptor.java:576-577)
  case $1 in default) echo 536870912 ;; *MiB) echo $(( ${1%MiB} * 1048576 )) ;; esac
}

say "cluster-run $RUN N=$N read=$DUR values=[${VALUES[*]}] start $(now) clone $(git -C $C describe --tags) $(git -C $C rev-parse --short HEAD) fcs-node.btm sha256 $(shasum -a 256 "$H/fcs-node.btm" | cut -c1-16) FcsSampler sha256 $(shasum -a 256 "$H/FcsSampler.java" | cut -c1-16)"
[ -n "$(ps -eo command | grep "[C]assandra""Daemon")" ] && { say "ABORT: a daemon is already running"; exit 1; }
mkdir -p "$BIN"; run javac -d "$BIN" "$H/FcsSampler.java" || die "javac FcsSampler"
rm -rf "$NODE"

# ---- LOAD phase (default file_cache_size)
conf default
start_node "$L/node/node-LOAD.out"
say "JVM $(grep -m1 -o 'JVM Arguments: .*' $L/node/system.log | grep -o -- '-Xm[sx][^,]*\|-XX:MaxDirectMemorySize=[^,]*\|-XX:NativeMemoryTracking=[a-z]*\|-javaagent:[^,]*\|-XX:+Use[A-Za-z0-9]*GC' | tr '\n' ' ')"
log "+ cassandra-stress write n=$N -col size=FIXED(512) n=FIXED(1) -schema replication(factor=1) compression=LZ4Compressor -rate threads=64 -node 127.0.0.1"
tmo 10800 "$C/tools/bin/cassandra-stress" write n=$N -col 'size=FIXED(512)' 'n=FIXED(1)' -schema 'replication(factor=1)' compression=LZ4Compressor -rate threads=64 -node 127.0.0.1 > "$L/stress-LOAD.txt" 2>&1 < /dev/null
rc=$?
say "STRESS LOAD exit=$rc $(grep -m1 'Total partitions' "$L/stress-LOAD.txt" | tr -s ' ') | $(grep -m1 'Total errors' "$L/stress-LOAD.txt" | tr -s ' ') | $(grep -m1 'Op rate' "$L/stress-LOAD.txt" | tr -s ' ') | $(grep -m1 'Total operation time' "$L/stress-LOAD.txt" | tr -s ' ')"
[ $rc -ne 0 ] && die "stress LOAD failed"
run nt flush keyspace1 || die "flush failed"
run ntl compact keyspace1 standard1 || die "compact failed"
idle_wait || die "not idle after load"
nt tablestats keyspace1.standard1 > "$L/tablestats-LOAD.txt" 2>&1
cqlsh_desc=$(HOME=$W/home tmo 120 "$C/bin/cqlsh" 127.0.0.1 -e "SELECT compression FROM system_schema.tables WHERE keyspace_name='keyspace1' AND table_name='standard1';" 2>&1 | tr -s ' \n' ' ')
say "LOAD tablestats: $(grep -E 'SSTable count|Space used \(live\)|Number of partitions|SSTable Compression Ratio' "$L/tablestats-LOAD.txt" | tr -s ' ' | tr '\n' ';') compression: $cqlsh_desc"
say "data dir bytes: $(du -sk "$NODE/data/keyspace1" | awk '{print $1*1024}')"
stop_node

# ---- one read run per value
for v in "${VALUES[@]}"; do
  conf "$v"
  exp=$(expected_cap "$v")
  off=$(stat -f %z "$L/node/system.log" 2>/dev/null || echo 0); echo "$off" > "$L/syslog-offset-$v.txt"
  start_node "$L/node/node-$v.out"
  tail -c +$((off+1)) "$L/node/system.log" > "$L/syslog-$v-start.txt"
  limit=$(grep -m1 'Global buffer pool limit is' "$L/syslog-$v-start.txt" | sed 's/^.*Global buffer pool limit/Global buffer pool limit/')
  cc=$(grep -m1 -o 'Initialized.*chunk cache\|ChunkCache.*' "$L/syslog-$v-start.txt" | head -1)
  rm -f "$L/.stop-cap"; java -cp "$BIN" FcsSampler 1000 "$L/.stop-cap" > "$L/capcheck-$v.txt" 2>&1 & cpid=$!; sleep 3; touch "$L/.stop-cap"; wait $cpid 2>/dev/null; rm -f "$L/.stop-cap"
  capv=$(head -1 "$L/capcheck-$v.txt" | grep -o 'cc_capacity=[0-9]*' | cut -d= -f2)
  nwcap=$(head -1 "$L/capcheck-$v.txt" | grep -o 'nw_capacity=[0-9]*' | cut -d= -f2)
  say "RUN $v start $(now) capacity=$capv expected=$exp networking_capacity=$nwcap limit_line=[$limit]"
  [ "$capv" = "$exp" ] || die "Capacity $capv != expected $exp for $v"
  echo "$limit" | grep -q 'for chunk-cache' || die "no 'Global buffer pool limit ... for chunk-cache' line for $v"
  rm -f "$L/.stop-sampler"
  java -cp "$BIN" FcsSampler 10000 "$L/.stop-sampler" > "$L/samples-$v.txt" 2> "$L/sampler-$v.err" & SPID=$!
  sleep 2
  t_start=$(perl -MTime::HiRes=time -e 'printf "%d\n", time*1000'); echo "$t_start" > "$L/stress-start-ms-$v.txt"
  log "+ cassandra-stress read duration=$DUR -pop dist=UNIFORM(1..$N) -col size=FIXED(512) n=FIXED(1) -rate threads=128 -node 127.0.0.1 > stress-$v.txt"
  tmo 3600 "$C/tools/bin/cassandra-stress" read duration=$DUR -pop "dist=UNIFORM(1..$N)" -col 'size=FIXED(512)' 'n=FIXED(1)' -rate threads=128 -node 127.0.0.1 > "$L/stress-$v.txt" 2>&1 < /dev/null
  rc=$?
  t_end=$(perl -MTime::HiRes=time -e 'printf "%d\n", time*1000'); echo "$t_end" > "$L/stress-end-ms-$v.txt"
  say "STRESS $v exit=$rc $(grep -m1 'Total partitions' "$L/stress-$v.txt" | tr -s ' ') | $(grep -m1 'Total errors' "$L/stress-$v.txt" | tr -s ' ') | $(grep -m1 'Op rate' "$L/stress-$v.txt" | tr -s ' ') | $(grep -m1 'Total operation time' "$L/stress-$v.txt" | tr -s ' ')"
  sleep 22   # two quiet samples after the read workload
  stop_sampler
  jcmd $PID VM.native_memory summary > "$L/nmt-$v.txt" 2>&1
  nt info > "$L/info-$v.txt" 2>&1
  tail -c +$((off+1)) "$L/node/system.log" > "$L/syslog-$v.txt"
  grep 'Maximum memory usage reached' "$L/syslog-$v.txt" > "$L/caplog-$v.txt"
  grep '^BMFC ' "$L/node/node-$v.out" > "$L/bmfc-$v.txt"
  last_slab=$(awk '$2=="SLAB" && $3=="chunk-cache" && $4>m{m=$4} END{print m+0}' "$L/bmfc-$v.txt")   # D1: the largest SLAB value
  nslab=$(awk '$2=="SLAB" && $3=="chunk-cache"' "$L/bmfc-$v.txt" | wc -l | tr -d ' ')
  q=$(tail -1 "$L/samples-$v.txt")
  say "RESULT $v pooled_exact=$last_slab slabs=$nslab samples=$(grep -c '^FCSS ' "$L/samples-$v.txt") cap_bm=[$(grep 'BMFC CAP chunk-cache' "$L/bmfc-$v.txt" | tr '\n' ';')] refuse_bm=[$(grep 'BMFC REFUSE chunk-cache' "$L/bmfc-$v.txt" | tr '\n' ';')] nw_bm=[$(grep -v 'chunk-cache' "$L/bmfc-$v.txt" | grep -v SLAB | tr '\n' ';')] caplog_chunk=$(grep -c 'for chunk-cache buffer pool' "$L/caplog-$v.txt") caplog_networking=$(grep -c 'for networking buffer pool' "$L/caplog-$v.txt") last_sample=[$q] chunk_cache_info=[$(grep -i 'chunk cache' "$L/info-$v.txt" | tr -s ' ')] nmt_other=[$(grep -m1 -- '- *Other' "$L/nmt-$v.txt" | tr -s ' ')] errors_syslog=$(grep -c '^ERROR' "$L/syslog-$v.txt")"
  stop_node
done

grep -c '^ERROR' "$L/node/system.log" > "$L/error-count.txt"; say "system.log ERROR lines: $(cat "$L/error-count.txt")"
stop_node
final_check
say "end $(now)"
