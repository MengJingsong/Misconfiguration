#!/usr/bin/env bash
# B8 arm (arm3 = arm2 + DROP_SSTABLES=1: remove the table sstables before restart, emulating a restore that replays logs not covered by sstables; arm2 = arm.sh + mid-replay class histograms, env HISTO_AFTER="s1 s2" seconds after the Replaying line): load phase (write, then kill -9) followed by a restart (commit-log replay) at the same budget.
#   arm.sh <run> <heapMiB> <map|blob> <size> <loadSecs> <inflight> [replay JVM opts ...]
# env: CONT_MIB (container, default 2 x heap), REPLAY_TIMEOUT (s, default 900), RATE (client cap, optional),
#      KEEP_DUMP=1 keep the .hprof (default: histogram then delete), LOAD_OPTS (JVM opts for the load phase)
# All data, logs and dumps under /mydata/b8/runs/<run>. Leaves nothing running.
set -uo pipefail
RUN=$1 HEAP=$2 KIND=$3 SIZE=$4 LSECS=$5 INFL=$6; shift 6; ROPTS="$*"
CONT=${CONT_MIB:-$((2*HEAP))} RTO=${REPLAY_TIMEOUT:-900}
C=/mydata/b8/cassandra H=/mydata/b8/harness R=/mydata/b8/runs/$RUN
mkdir -p "$R"/{load,replay,dumps}; LOG=$R/arm.log
log() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
dpid() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' | head -1; }
start_node() { # phase opts
  local ph=$1; shift
  ( cd $C; export MAX_HEAP_SIZE=${HEAP}M JVM_EXTRA_OPTS="$*" CASSANDRA_HEAPDUMP_DIR=$R/dumps
    systemd-run --user --scope -p MemoryMax=${CONT}M -p MemorySwapMax=0 --unit=b8-$RUN-$ph-$(date +%s) -- bin/cassandra -f > $R/$ph/stdout.txt 2>&1 ) &
  for i in $(seq 1 30); do P=$(dpid); [ -n "$P" ] && break; sleep 1; done
  CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$P/cgroup)
  log "$ph: pid=$P cg=$CG max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max) opts='$*'"
  ( while kill -0 $P 2>/dev/null; do echo "$(date +%s) $(cat $CG/memory.current 2>/dev/null)"; sleep 1; done ) > $R/$ph/memcur.txt &
}
stop_node() {
  local P=$(dpid); [ -z "$P" ] && return
  kill $P; for i in $(seq 1 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
  kill -0 $P 2>/dev/null && kill -9 $P; sleep 2
}
[ -n "$(dpid)" ] && { log "ABORT: a daemon is running"; exit 1; }
log "== arm $RUN heap=${HEAP}M container=${CONT}M kind=$KIND size=$SIZE load=${LSECS}s inflight=$INFL rate=${RATE:-none} replay-opts='$ROPTS' arch=$(uname -m)"
rm -rf $C/data $C/logs; mkdir -p $C/logs
# ---- load phase
start_node load ${LOAD_OPTS:-}
for i in $(seq 1 300); do grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null && break; sleep 1; done
log "load: node up after ${i}s"
$H/load.sh schema 127.0.0.1 >> $R/load/client.txt 2>&1
$H/load.sh run $KIND $SIZE $INFL $((LSECS+60)) 0 127.0.0.1 ${RATE:-} >> $R/load/client.txt 2>&1 &
CLI=$!
T0=$(date +%s)
while [ $(( $(date +%s) - T0 )) -lt $LSECS ]; do
  [ -z "$(dpid)" ] && { log "load: NODE DIED during load"; break; }
  { echo "== $(date +%T) t=$(( $(date +%s) - T0 ))"; $C/bin/nodetool tablestats b8.t_$KIND 2>/dev/null | grep -E 'Memtable (cell count|data size|off heap)|Memtable switch|SSTable count'; \
    $C/bin/nodetool tpstats 2>/dev/null | grep -E 'MemtableFlushWriter|MutationStage|Native-Transport'; \
    echo "commitlog_MiB=$(du -sm $C/data/commitlog | cut -f1)"; } >> $R/load/stats.txt 2>&1
  sleep 5
done
P=$(dpid); log "load: kill -9 $P at t=$(( $(date +%s) - T0 ))s; commitlog $(du -sm $C/data/commitlog | cut -f1) MiB, $(ls $C/data/commitlog | wc -l) files"
[ -n "$P" ] && kill -9 $P; sleep 3; kill $CLI 2>/dev/null; wait $CLI 2>/dev/null
tail -3 $R/load/client.txt | tee -a $LOG
cp $C/logs/system.log $C/logs/gc.log* $R/load/ 2>/dev/null
log "load: client errors: $(grep -c . $R/load/client.txt) lines; OOM in load: $(grep -c "java.lang.OutOfMemoryError" $R/load/stdout.txt $C/logs/system.log 2>/dev/null | tr '\n' ' ')"
ls -l $C/data/commitlog > $R/load/commitlog-ls.txt
if [ "${DROP_SSTABLES:-0}" = 1 ]; then n=$(ls $C/data/data/b8/t_$KIND-*/*-Data.db 2>/dev/null | wc -l); rm -f $C/data/data/b8/t_$KIND-*/nb-*; log "restore emulation: removed $n sstables of b8.t_$KIND (no sstable covers the log)"; fi
rm -f $C/logs/system.log $C/logs/debug.log $C/logs/gc.log*
# ---- replay phase
start_node replay $ROPTS
T1=$(date +%s); OUT=timeout
while [ $(( $(date +%s) - T1 )) -lt $RTO ]; do
  if grep -q 'Starting listening for CQL clients' $C/logs/system.log 2>/dev/null; then OUT=started; break; fi
  if [ -z "${TREP:-}" ] && grep -q 'CommitLog.java:206 - Replaying' $C/logs/system.log 2>/dev/null; then TREP=$(date +%s); log "replay: Replaying seen"; fi
  if [ -n "${TREP:-}" ]; then for hs in ${HISTO_AFTER:-}; do
    if [ $(( $(date +%s) - TREP )) -ge $hs ] && [ ! -f $R/replay/histo-$hs.txt ]; then
      timeout 180 jcmd $(dpid) GC.class_histogram > $R/replay/histo-$hs.txt 2>&1
      log "replay: histogram +${hs}s: total $(awk '/^Total/{printf "%.0f MiB", $3/1048576}' $R/replay/histo-$hs.txt) live; Mutation n=$(awk '$4=="org.apache.cassandra.db.Mutation"{print $2}' $R/replay/histo-$hs.txt)"
    fi; done; fi
  if [ -z "$(dpid)" ]; then OUT=died; break; fi
  sleep 1
done
log "replay: outcome=$OUT after $(( $(date +%s) - T1 ))s"
grep -E 'Replaying|Log replay complete|OutOfMemory|Dumping heap|Heap dump file|ERROR' $C/logs/system.log $R/replay/stdout.txt 2>/dev/null | cut -c1-300 | head -20 | tee -a $LOG
grep -h 'oom' $CG/memory.events 2>/dev/null | tr '\n' ' ' | sed 's/^/replay memory.events: /' | tee -a $LOG; echo | tee -a $LOG
[ $OUT = started ] && { $C/bin/nodetool tablestats b8.t_$KIND 2>/dev/null | grep -E 'Memtable (cell count|data size)|SSTable count' >> $R/replay/stats.txt; }
stop_node
sleep 2
cp $C/logs/system.log $C/logs/gc.log* $R/replay/ 2>/dev/null
python3 $H/gcsum.py $R/load/gc.log > $R/load/gcsum.txt 2>&1
python3 $H/gcsum.py $R/replay/gc.log > $R/replay/gcsum.txt 2>&1
log "load gc: $(tail -1 $R/load/gcsum.txt)"
log "replay gc: $(tail -1 $R/replay/gcsum.txt)"
log "replay mem.current max: $(sort -k2 -n $R/replay/memcur.txt | tail -1 | cut -d' ' -f2) B"
for f in $R/dumps/*.hprof; do [ -f "$f" ] || continue
  python3 $H/hprofhist.py "$f" 30 > $R/dumps/hist-$(basename $f .hprof).txt 2>&1
  log "dump $(du -m $f | cut -f1) MiB -> hist: $(head -1 $R/dumps/hist-$(basename $f .hprof).txt)"
  [ "${KEEP_DUMP:-0}" = 1 ] || rm -f "$f"
done
log "left: daemon=$(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon') client=$(pgrep -fc '[B]8Load')"
log "== RESULT $RUN heap=$HEAP $KIND/$SIZE replay=$OUT"
