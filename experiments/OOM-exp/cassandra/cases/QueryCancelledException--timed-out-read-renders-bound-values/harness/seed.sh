#!/usr/bin/env bash
# U16 SEED (from R12's): start the base tree empty at 4 GiB, create schema, load k=1..4, flush, compact, drain, stop, tar data.
set -u
W=/mydata/s4/u16; H=$W/harness; T=$W/cassandra-base; R=$W/runs/SEED
mkdir -p $R $W/seed; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=4G CASSANDRA_HEAPDUMP_DIR=$R exec systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=u16-SEED -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do sleep 2; [ -z "$PID" ] && PID=$(pgrep -f CassandraDaemon | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break; done
log "daemon pid $PID up"
python3 -I $H/client.py --ddl; sleep 2
python3 -I $H/client.py --load --conns 16
$T/bin/nodetool flush u16; log flushed
$T/bin/nodetool compact u16; log compacted
$T/bin/nodetool tablestats u16.t | head -40
ls -l $T/data/data/u16/t-*/
$T/bin/nodetool drain; log drained
kill $PID; for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done; kill -0 $PID 2>/dev/null && kill -9 $PID
cp $T/logs/system.log $R/
rm -rf $T/logs
tar -C $T -cf $W/seed/data.tar data && ls -l $W/seed/data.tar
rm -rf $T/data
log "SEED done"
