#!/usr/bin/env bash
# C1 run3 arm runner (on apt140, co-located with victim but OUTSIDE its cgroup).
# Keyspace NTS {v:1,f:1} -> every write replicates to victim (10.10.1.1) AND the fast
# co-replica (10.10.1.2). CL=ONE -> client acks on the FAST replica, never blocks on the
# slow victim. The coordinator still sends each mutation to the victim; the slow victim's
# receive queue floods toward the ceiling. OPEN-LOOP generator: `-rate fixed=<r>/s` sends
# at a fixed offered rate regardless of victim completion (point 2 of the plan review).
#   arm3.sh <tag> <whitelistCSV> <threads> <fixedPerSec> <durSec> <blobBytes>
set -uo pipefail
BUILD=$HOME/cassandra-b1
IP=10.10.1.1
ROOT=/mydata/c1r3
tag=$1 wl=$2 threads=$3 rate=$4 dur=$5 blob=${6:-1048576}
D=$ROOT/arms/$tag; mkdir -p "$D"
cql(){ "$BUILD/bin/cqlsh" "$IP" --request-timeout=30 -e "$1" 2>&1; }
vpid(){ pgrep -f "cassandra.logdir=$ROOT/victim/logs" | head -1; }
cgdir(){ local p=$(vpid); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)"; }
log(){ echo "[$(date '+%T')] $*" | tee -a "$D/arm.log"; }

P=$(vpid); CG=$(cgdir)
N=$(echo "$wl" | tr ',' '\n' | grep -c .)
log "arm=$tag N=$N wl=[$wl] threads=$threads fixed=${rate}/s dur=${dur}s blob=$blob vpid=$P"
echo "$wl" | tr ',' '\n' | awk '{print NR": "$0}' > "$D/coordinators.txt"

# victim RSS/cgroup sampler
echo "epoch_ms,rssAnonKB,mem_current,oom,oom_kill" > "$D/mem.csv"
( end=$((SECONDS+dur+30))
  while [ $SECONDS -lt $end ]; do
    p=$(vpid); e=$(date +%s%3N); ra=NA mc=NA oom=NA ok=NA
    [ -r /proc/$p/status ] && ra=$(awk '/^RssAnon:/{print $2}' /proc/$p/status)
    if [ -n "$CG" ] && [ -r "$CG/memory.current" ]; then mc=$(cat "$CG/memory.current"); oom=$(awk '/^oom /{print $2}' "$CG/memory.events"); ok=$(awk '/^oom_kill /{print $2}' "$CG/memory.events"); fi
    echo "$e,$ra,$mc,$oom,$ok" >> "$D/mem.csv"; sleep 1
  done ) & MEMPID=$!

# victim inbound-queue sampler (throttled_count + expired_count are the key run-3 signals)
( end=$((SECONDS+dur+30))
  while [ $SECONDS -lt $end ]; do
    echo "@ $(date +%s%3N)" >> "$D/queue.log"
    "$BUILD/bin/cqlsh" "$IP" --request-timeout=15 -e \
      "SELECT address,using_bytes,using_reserve_bytes,throttled_count,received_count,processed_count,expired_count FROM system_views.internode_inbound;" 2>>"$D/queue.err" \
      | grep -E '10\.10\.1\.|rows\)' >> "$D/queue.log"
    sleep 2
  done ) & QPID=$!

log "stress start (NTS v:1,f:1, CL=ONE, open-loop fixed=${rate}/s)"
( ulimit -n 100000
  JVM_OPTS="-Xmx8G -Xms2G -Xss256k" "$BUILD/tools/bin/cassandra-stress" write no-warmup duration=${dur}s cl=ONE \
    -schema "replication(strategy=NetworkTopologyStrategy,v=1,f=1)" keyspace=keyspace1 \
    -col "size=FIXED($blob) n=FIXED(1)" \
    -mode native cql3 \
    -rate "fixed=${rate}/s" "threads=$threads" \
    -node whitelist "$wl" \
    -log file="$D/stress.log" ) > "$D/stress.out" 2>&1
SRC=$?
log "stress exit rc=$SRC"

sleep 3
wait $MEMPID 2>/dev/null; wait $QPID 2>/dev/null

log "final queue snapshot"
cql "SELECT address,using_bytes,using_reserve_bytes,throttled_count,throttled_nanos,received_count,processed_count,scheduled_count,expired_count FROM system_views.internode_inbound;" > "$D/qfinal.txt"
if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then jcmd "$P" VM.native_memory summary > "$D/nmt-final.txt" 2>&1; fi

log "=== PEAKS ==="
awk -F, 'NR>1 && $2!="NA"{if($2+0>mra){mra=$2}; if($3!="NA"&&$3+0>mmc){mmc=$3}} END{printf "peak_rssAnon=%.0fMiB peak_mem_current=%.0fMiB\n", mra/1024, mmc/1048576}' "$D/mem.csv" | tee -a "$D/arm.log"
echo "oom_events=$(awk -F, 'END{print $4" oom_kill="$5}' "$D/mem.csv")" | tee -a "$D/arm.log"
log "inbound peers (addr using reserve throttled received processed expired):"; grep -E '10\.10\.1\.' "$D/qfinal.txt" | tee -a "$D/arm.log" | head -40
echo "=== OOM check ==="; grep -nE 'OutOfMemoryError|Direct buffer memory|forceHeapSpaceOom' "$ROOT/victim/logs/system.log" 2>/dev/null | tail -8 | tee -a "$D/arm.log"
P2=$(vpid); if [ -n "$P2" ] && kill -0 "$P2" 2>/dev/null; then log "victim ALIVE pid=$P2"; else log "victim NOT RUNNING (check OOM)"; fi
log "arm $tag done"
