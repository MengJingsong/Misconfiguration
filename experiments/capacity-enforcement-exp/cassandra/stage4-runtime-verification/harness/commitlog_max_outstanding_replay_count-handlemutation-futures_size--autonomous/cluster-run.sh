#!/usr/bin/env bash
# Cluster tier (B3e as amended) of case o100. On pc82, one invocation at a time:
#   bash cluster-run.sh load                                 # B3e.1
#   bash cluster-run.sh replay <label> "<JVM_EXTRA_OPTS>"    # B3e.2 run()
# All paths are literal under /mydata/jingsong-cass-s4/o100; only the node whose PID this script recorded is signalled.
set -uo pipefail
SRC=/mydata/jingsong-cass-s4/o100/c509-node
RUN=/mydata/jingsong-cass-s4/o100/replay-count
H=$(cd "$(dirname "$0")" && pwd)
MODE=$1; LABEL=${2:-load}; OPTS=${3:-}
OUT=/mydata/jingsong-cass-s4/o100/cluster/$LABEL; mkdir -p "$OUT" "$RUN"
exec > >(tee -a "$OUT/session.txt") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
NT="$SRC/bin/nodetool -h 127.0.0.1 -p 7199"
export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_LOG_DIR=$RUN/logs
stopnode() {
  [ -s $RUN/pid ] || return 0; local p; p=$(cat $RUN/pid)
  if [ -d /proc/$p ] && grep -q CassandraDaemon /proc/$p/cmdline 2>/dev/null; then
    log "kill $p"; kill $p; for i in $(seq 1 15); do [ -d /proc/$p ] || break; sleep 1; done
    [ -d /proc/$p ] && { log "kill -9 $p"; kill -9 $p; sleep 2; }
  fi
  [ -d /proc/$p ] && log "WARNING $p alive" || log "node $p gone"
}
die() { log "FAIL: $*"; stopnode; exit 1; }
portcheck() { if ss -ltn | grep -E ':(7000|7199|9042)\b'; then die "ports busy"; fi; log "ports 7000/7199/9042 free"; }
start() {  # $1 = JVM_EXTRA_OPTS
  ulimit -n 100000; log "ulimit -n $(ulimit -n)"; portcheck; mkdir -p $RUN/logs; rm -f /mydata/jingsong-cass-s4/o100/replay-count/pid
  log "start JVM_EXTRA_OPTS=\"$1\" MAX_HEAP_SIZE=$MAX_HEAP_SIZE HEAP_NEWSIZE=$HEAP_NEWSIZE"
  ( cd $SRC && JVM_EXTRA_OPTS="$1" setsid nohup bin/cassandra -p $RUN/pid </dev/null > $OUT/cassandra.out 2>&1 & )
  for i in $(seq 1 30); do [ -s $RUN/pid ] && break; sleep 1; done; [ -s $RUN/pid ] || die "no pid"; log "pid $(cat $RUN/pid)"
}
waitcql() {
  for i in $(seq 1 300); do
    [ -d /proc/$(cat $RUN/pid) ] || die "daemon died during start"
    [ "$($NT statusbinary 2>/dev/null | tr -d '[:space:]')" = running ] && { log "statusbinary running"; return 0; }; sleep 2
  done; die "CQL not up"
}
if [ "$MODE" = load ]; then
  [ -e $RUN/snap.tar ] && die "snapshot exists"
  python3 $H/mkconf.py $SRC $RUN; awk '/o100 stage-4 settings/,0' $SRC/conf/cassandra.yaml
  mkdir -p $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches $RUN/cdc_raw $RUN/logs
  start ""; waitcql
  cd $SRC
  log "stress n=1 with schema"
  tools/bin/cassandra-stress write n=1 no-warmup -rate threads=1 -col 'n=FIXED(1)' 'size=FIXED(64)' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node 127.0.0.1 > $OUT/stress-n1.txt 2>&1; log "exit $?"
  log "nodetool flush"; $NT flush; log "exit $?"
  log "stress n=300000"
  tools/bin/cassandra-stress write n=300000 no-warmup -rate threads=32 -col 'n=FIXED(1)' 'size=FIXED(64)' -node 127.0.0.1 > $OUT/stress.txt 2>&1; log "exit $?"
  grep -E 'Total errors|Total partitions|Op rate|Total operation time' $OUT/stress.txt
  sleep 5
  $NT tablestats keyspace1.standard1 > $OUT/tablestats.txt 2>&1; grep -E 'SSTable count|Memtable cell count|Memtable data size|Local write count' $OUT/tablestats.txt
  p=$(cat $RUN/pid); log "kill -9 $p"; kill -9 $p; sleep 2; [ -d /proc/$p ] && die "alive"; log "stopped"
  cp $RUN/logs/system.log $OUT/system.log; ls -l $RUN/commitlog > $OUT/commitlog-ls.txt; du -sb $RUN/commitlog $RUN/data | tee -a $OUT/commitlog-ls.txt
  rm -f /mydata/jingsong-cass-s4/o100/replay-count/pid
  tar -C $RUN -cf $RUN/snap.tar data commitlog hints saved_caches; ls -l $RUN/snap.tar
  log "LOAD done"; exit 0
fi
if [ "$MODE" = replay ]; then
  [ -s $RUN/pid ] && stopnode
  rm -rf /mydata/jingsong-cass-s4/o100/replay-count/data /mydata/jingsong-cass-s4/o100/replay-count/commitlog \
         /mydata/jingsong-cass-s4/o100/replay-count/hints /mydata/jingsong-cass-s4/o100/replay-count/saved_caches \
         /mydata/jingsong-cass-s4/o100/replay-count/logs
  tar -C $RUN -xf $RUN/snap.tar; mkdir -p $RUN/logs
  start "$OPTS"; P=$(cat $RUN/pid)
  python3 $H/sampler.py $P $RUN/logs/system.log $OUT/samples.jsonl $OUT/samples-raw.txt "$NT"; log "sampler exit $?"
  ps -o args= -p $P | tr ' ' '\n' | grep -E 'replay|javaagent|Xmx' > $OUT/jvm-args.txt; cat $OUT/jvm-args.txt
  grep -E 'Replaying |Log replay complete' $RUN/logs/system.log | cut -c1-250
  stopnode
  cp $RUN/logs/system.log $OUT/system.log; grep -c '^ERROR' $OUT/system.log | sed 's/^/ERROR lines: /'
  pgrep -f CassandraDaemon >/dev/null && log "LEFTOVER CassandraDaemon" || log "no CassandraDaemon"
  log "REPLAY done $LABEL"; exit 0
fi
