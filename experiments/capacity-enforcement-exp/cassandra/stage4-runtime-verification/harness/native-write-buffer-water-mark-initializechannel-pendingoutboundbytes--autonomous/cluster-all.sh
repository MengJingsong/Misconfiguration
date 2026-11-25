#!/bin/bash
# B3e as amended (S4-A5): one node from the built copy, insert, warm-up, cells A B C D, repeat of B, stop.
set -u
T=/mydata/jingsong-cass-s4/o133/c509; H=/mydata/jingsong-cass-s4/o133/harness; R=/mydata/jingsong-cass-s4/o133/cluster/run1
mkdir -p $R; S=$R/session.txt
log(){ echo "### $(date -u +%FT%T.%3NZ) $(date +%s%3N) $*" >> $S; }
run(){ log "+ $*"; "$@" >> $S 2>&1; }
cd $T
run python3 $H/mkconf.py $T
ulimit -n 100000
log "start node"
( MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=1G" bin/cassandra -p $T/pid > $T/out.log 2>&1 )
for i in $(seq 1 90); do
  sleep 2; [ -f $T/pid ] && ! kill -0 $(cat $T/pid) 2>/dev/null && { log "daemon died"; exit 1; }
  bin/nodetool -p 17199 statusbinary 2>/dev/null | grep -qx running && break   # D2: exact match ('not running' contains 'running')
done
run bin/nodetool -p 17199 status; run bin/nodetool -p 17199 statusbinary
bin/nodetool -p 17199 statusbinary 2>/dev/null | grep -qx running || { log "binary not running: abort"; exit 1; }
PID=$(cat $T/pid); log "pid=$PID"; tr '\0' '\n' < /proc/$PID/cmdline | grep -E 'Xmx|Xms|NativeMemory|MaxDirect|netty' > $R/jvm-args.txt
cat /proc/sys/net/ipv4/tcp_wmem > $R/tcp_wmem.txt; cat /proc/sys/net/ipv4/tcp_rmem > $R/tcp_rmem.txt
run python3 $H/wm_client.py --port 19142 --mode insert
grep -q "^inserted" $S || { log "insert failed: abort"; exit 1; }
run bin/nodetool -p 17199 flush wm
log "warm-up"; run python3 $H/wm_client.py --port 19142 --mode read --k 256
grep -q "^read bytes" $S || { log "warm-up failed: abort"; exit 1; }
sleep 30
$H/cluster-cell.sh A flood 64 0
$H/cluster-cell.sh B flood 256 0
$H/cluster-cell.sh C flood 256 64
$H/cluster-cell.sh D read 256 0
$H/cluster-cell.sh B-rep flood 256 0
log "stop node"; kill $(cat $T/pid)
for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
kill -0 $PID 2>/dev/null && { log "still alive, kill -9"; kill -9 $PID; }
cp $T/logs/system.log $R/system.log; cp $T/out.log $R/cassandra.out
log "ALL DONE"
