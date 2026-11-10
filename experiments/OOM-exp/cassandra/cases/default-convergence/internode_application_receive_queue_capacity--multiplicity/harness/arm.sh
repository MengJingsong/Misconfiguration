#!/usr/bin/env bash
# C1 OOM-exp arm runner (on apt140, co-located with victim but OUTSIDE its cgroup).
# Drives cassandra-stress large-mutation writes through a whitelist of N coordinator
# peers (so exactly N peers coordinate -> N inbound handlers on the victim), while
# sampling the victim's internode receive queues, reserve, direct memory, RSS, cgroup.
#   arm.sh <tag> <whitelistCSV> <threads> <throttlePerSec|0> <durSec> <blobBytes>
set -uo pipefail
BUILD=$HOME/cassandra-b1
V=/mydata/c1/victim
IP=10.10.1.1
tag=$1 wl=$2 threads=$3 thr=$4 dur=$5 blob=${6:-131072}
D=/mydata/c1/arms/$tag; mkdir -p "$D"
cql(){ "$BUILD/bin/cqlsh" "$IP" --request-timeout=30 -e "$1" 2>&1; }
vpid(){ pgrep -f "cassandra.logdir=$V/logs" | head -1; }
cgdir(){ local p=$(vpid); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)"; }
log(){ echo "[$(date '+%T')] $*" | tee -a "$D/arm.log"; }

P=$(vpid); CG=$(cgdir)
log "arm=$tag wl=[$wl] threads=$threads throttle=$thr dur=${dur}s blob=$blob vpid=$P"
echo "$wl" | tr ',' '\n' | awk '{print NR": "$0}' > "$D/coordinators.txt"
N=$(echo "$wl" | tr ',' '\n' | grep -c .)

# throttle clause
rate="threads=$threads"; [ "$thr" != 0 ] && rate="threads=$threads throttle=$thr/s"

# background cheap sampler: epoch,rssAnonKB,mem_current,oom,oom_kill,directMaxReservedPeak
echo "epoch_ms,rssAnonKB,mem_current,oom,oom_kill" > "$D/mem.csv"
( end=$((SECONDS+dur+20))
  while [ $SECONDS -lt $end ]; do
    p=$(vpid); e=$(date +%s%3N); ra=NA mc=NA oom=NA ok=NA
    [ -r /proc/$p/status ] && ra=$(awk '/^RssAnon:/{print $2}' /proc/$p/status)
    if [ -n "$CG" ] && [ -r "$CG/memory.current" ]; then mc=$(cat "$CG/memory.current"); oom=$(awk '/^oom /{print $2}' "$CG/memory.events"); ok=$(awk '/^oom_kill /{print $2}' "$CG/memory.events"); fi
    echo "$e,$ra,$mc,$oom,$ok" >> "$D/mem.csv"; sleep 1
  done ) & MEMPID=$!

# background queue sampler (virtual table) ~ every 2s
( end=$((SECONDS+dur+20))
  while [ $SECONDS -lt $end ]; do
    echo "@ $(date +%s%3N)" >> "$D/queue.log"
    "$BUILD/bin/cqlsh" "$IP" --request-timeout=15 -e \
      "SELECT address,using_bytes,using_reserve_bytes,throttled_count,received_count,processed_count FROM system_views.internode_inbound;" 2>>"$D/queue.err" \
      | grep -E '10\.10\.1\.|rows\)' >> "$D/queue.log"
    sleep 2
  done ) & QPID=$!

# the workload (time-capped)
log "stress start"
( ulimit -n 100000
  "$BUILD/tools/bin/cassandra-stress" write duration=${dur}s cl=ONE \
    -schema "replication(strategy=SimpleStrategy,factor=${RF:-9})" keyspace=keyspace1 \
    -col "size=FIXED($blob) n=FIXED(1)" \
    -mode native cql3 \
    -rate $rate \
    -node whitelist "$wl" \
    -log file="$D/stress.log" ) > "$D/stress.out" 2>&1
SRC=$?
log "stress exit rc=$SRC"

sleep 3
wait $MEMPID 2>/dev/null; wait $QPID 2>/dev/null

# final snapshots
log "final queue snapshot"
cql "SELECT address,using_bytes,using_reserve_bytes,throttled_count,throttled_nanos,received_count,processed_count,scheduled_count,expired_count FROM system_views.internode_inbound;" > "$D/qfinal.txt"
if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then jcmd "$P" VM.native_memory summary > "$D/nmt-final.txt" 2>&1; fi

# peaks
log "=== PEAKS ==="
awk -F, 'NR>1 && $2!="NA"{if($2+0>mra){mra=$2}; if($3!="NA"&&$3+0>mmc){mmc=$3}} END{printf "peak_rssAnon=%.0fMiB peak_mem_current=%.0fMiB\n", mra/1024, mmc/1048576}' "$D/mem.csv" | tee -a "$D/arm.log"
echo "oom_events=$(awk -F, 'END{print $4" oom_kill="$5}' "$D/mem.csv")" | tee -a "$D/arm.log"
# distinct coordinators actually seen inbound (received_count>0 excluding self)
log "inbound peers with traffic:"; grep -E '10\.10\.1\.' "$D/qfinal.txt" | awk '{print $1, $2, $3}' | tee -a "$D/arm.log" | head -40
echo "=== OOM check ==="; grep -nE 'OutOfMemoryError|Direct buffer memory|forceHeapSpaceOom' "$V/logs/system.log" 2>/dev/null | tail -8 | tee -a "$D/arm.log"
P2=$(vpid); if [ -n "$P2" ] && kill -0 "$P2" 2>/dev/null; then log "victim ALIVE pid=$P2"; else log "victim NOT RUNNING (check OOM)"; fi
log "arm $tag done"
