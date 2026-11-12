#!/usr/bin/env bash
# Cluster tier (B3) of case o32, amendments M1-M5. Run on the stage-4 node, one invocation at a time:
#   bash cluster-run.sh load                          # B3e.1: load 24000 x 64 KiB, kill -9, save pristine copy
#   bash cluster-run.sh replay <label> <bytes> <count> # B3e.3/4: restore pristine, start with the knob, sample until replay completes, stop
# Everything lives under $BASE; only processes whose PID this script recorded are signalled.
set -uo pipefail
BASE=/mydata/jingsong-cass-s4/o32
TREE=$BASE/node-tree
NODE=$BASE/node
PRIS=$BASE/pristine
RUNS=$BASE/cluster
HERE=$(cd "$(dirname "$0")" && pwd)
MODE=$1
mkdir -p "$RUNS"
LABEL=${2:-load}
OUT=$RUNS/$LABEL
mkdir -p "$OUT"
exec > >(tee -a "$OUT/session.txt") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
die() { log "FAIL: $*"; stopnode; exit 1; }
NT="$TREE/bin/nodetool -h 127.0.0.1 -p 7499"
PIDF=$NODE/pid
stopnode() {
  [ -f "$PIDF" ] || return 0
  local p; p=$(cat "$PIDF")
  if [ -d /proc/$p ] && grep -q CassandraDaemon /proc/$p/cmdline 2>/dev/null; then
    log "SIGTERM $p"; kill "$p"
    for i in $(seq 1 60); do [ -d /proc/$p ] || break; sleep 1; done
    if [ -d /proc/$p ]; then log "SIGKILL $p"; kill -9 "$p"; sleep 2; fi
  fi
  [ -d /proc/$p ] && log "WARNING: $p still alive" || log "node $p gone"
}
startnode() {
  ulimit -n 100000 2>/dev/null || ulimit -n "$(ulimit -Hn)"
  log "ulimit -n $(ulimit -n)"
  mkdir -p "$NODE/logs"
  log "start: MAX_HEAP_SIZE=6G HEAP_NEWSIZE=1200M CASSANDRA_LOG_DIR=$NODE/logs bin/cassandra -p $PIDF"
  ( cd "$TREE" && MAX_HEAP_SIZE=6G HEAP_NEWSIZE=1200M CASSANDRA_LOG_DIR=$NODE/logs setsid nohup bin/cassandra -p "$PIDF" < /dev/null > "$OUT/cassandra.out" 2>&1 & )
  for i in $(seq 1 30); do [ -s "$PIDF" ] && break; sleep 1; done
  [ -s "$PIDF" ] || die "no pid file"
  log "pid $(cat "$PIDF")"
}
waitcql() {
  for i in $(seq 1 300); do
    [ -d /proc/$(cat "$PIDF") ] || die "daemon died during start"
    s=$($NT statusbinary 2>/dev/null | tr -d '[:space:]')
    [ "$s" = running ] && { log "statusbinary running"; return 0; }
    sleep 2
  done
  die "CQL port not up"
}
if [ "$MODE" = load ]; then
  log "LOAD phase"
  [ -e "$NODE" ] && die "$NODE exists"
  python3 "$HERE/mkconf.py" "$TREE" "$NODE" load
  grep -A30 'o32 stage-4 settings' "$TREE/conf/cassandra.yaml"; tail -3 "$TREE/conf/jvm-server.options"; grep '^JMX_PORT' "$TREE/conf/cassandra-env.sh"
  mkdir -p "$NODE"
  startnode; waitcql
  log "instrument check: sampler on the idle load node for about 7 s (expect ok=true, small Mutation count)"
  timeout 7 python3 "$HERE/sampler.py" "$(cat "$PIDF")" /nonexistent "$OUT/sampler-check.jsonl"; cat "$OUT/sampler-check.jsonl"
  log "stress write n=24000"
  ( cd "$TREE" && tools/bin/cassandra-stress write n=24000 no-warmup -rate threads=16 -col 'n=FIXED(1)' 'size=FIXED(65536)' -node 127.0.0.1 -port native=9342 jmx=7499 ) > "$OUT/stress.txt" 2>&1
  log "stress exit=$?"; grep -E 'Total errors|Total partitions|Op rate|Total operation time' "$OUT/stress.txt"
  $NT tablestats keyspace1.standard1 > "$OUT/tablestats.txt" 2>&1; grep -E 'SSTable count|Memtable cell count|Memtable data size|Local write count' "$OUT/tablestats.txt"
  grep -q 'SSTable count: 0' "$OUT/tablestats.txt" || die "SSTables present"
  log "sleep 15 (periodic sync 10 s)"; sleep 15
  p=$(cat "$PIDF"); log "kill -9 $p"; kill -9 "$p"; for i in $(seq 1 30); do [ -d /proc/$p ] || break; sleep 1; done
  [ -d /proc/$p ] && die "still alive"
  cp "$NODE/logs/system.log" "$OUT/system.log"
  ls -l "$NODE/commitlog" > "$OUT/commitlog-ls.txt"; du -sb "$NODE/commitlog" "$NODE/data" | tee -a "$OUT/commitlog-ls.txt"
  rm -f "$PIDF"
  log "save pristine"; rsync -a "$NODE/" "$PRIS/"; du -sb "$PRIS"
  log "LOAD done"; exit 0
fi
if [ "$MODE" = replay ]; then
  BYTES=$3; COUNT=$4
  log "REPLAY label=$LABEL bytes=$BYTES count=$COUNT"
  ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -F "$TREE" && die "a node of this tree is running"
  rsync -a --delete "$PRIS/" "$NODE/"; rm -f "$PIDF" "$NODE/logs/"*
  python3 "$HERE/mkconf.py" "$TREE" "$NODE" replay "$BYTES" "$COUNT"
  grep -A30 'o32 stage-4 settings' "$TREE/conf/cassandra.yaml" | grep -E 'memtable|concurrent|commitlog'; tail -3 "$TREE/conf/jvm-server.options"
  startnode
  P=$(cat "$PIDF")
  log "sampler start"
  python3 "$HERE/sampler.py" "$P" "$NODE/logs/system.log" "$OUT/samples.jsonl"
  log "sampler end"
  for i in $(seq 1 600); do grep -q 'Log replay complete' "$NODE/logs/system.log" 2>/dev/null && break; [ -d /proc/$P ] || break; sleep 1; done
  grep -E 'Replaying |Log replay complete' "$NODE/logs/system.log" | cut -c1-300
  tr ' ' '\n' < /proc/$P/cmdline 2>/dev/null | true
  ps -o args= -p "$P" | tr ' ' '\n' | grep -E 'replay|Xmx|Xms' 
  sleep 3
  stopnode
  cp "$NODE/logs/system.log" "$OUT/system.log"; cp "$NODE/logs/gc.log"* "$OUT/" 2>/dev/null
  grep -c '^ERROR' "$OUT/system.log" | sed 's/^/ERROR lines: /'
  rm -f "$PIDF"
  log "REPLAY done"; exit 0
fi
