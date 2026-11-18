# B15 shared functions (start_node/stop_node/sampler from B8 arm3.sh). Sourced by mkimg.sh and replay.sh.
W=/mydata/s4/b15-w3; C=$W/cassandra; H=$W/harness
log() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
dpid() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' | head -1; }
start_node() { # <outdir> <heapMiB> <unit> [JVM opts]
  local O=$1 HP=$2 U=$3; shift 3
  ( cd $C; export MAX_HEAP_SIZE=${HP}M JVM_EXTRA_OPTS="$*" CASSANDRA_HEAPDUMP_DIR=$O/dumps
    exec systemd-run --user --scope -p MemoryMax=$((HP+4096))M -p MemorySwapMax=0 --unit=$U-$(date +%s) -- bin/cassandra -f > $O/stdout.txt 2>&1 ) &
  for i in $(seq 1 30); do P=$(dpid); [ -n "$P" ] && break; sleep 1; done
  CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$P/cgroup)
  log "start: pid=$P cg=$CG max=$(cat $CG/memory.max) swap.max=$(cat $CG/memory.swap.max) heap=${HP}M opts='$*'"
  ( while kill -0 $P 2>/dev/null; do echo "$(date +%s) $(cat $CG/memory.current 2>/dev/null)"; tr "\n" " " < $CG/memory.events 2>/dev/null > $O/memevents.tmp && mv $O/memevents.tmp $O/memevents.txt; sleep 1; done ) > $O/memcur.txt &
}
stop_node() {
  local P=$(dpid); [ -z "$P" ] && return
  kill $P; for i in $(seq 1 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
  kill -0 $P 2>/dev/null && kill -9 $P; sleep 2
}
