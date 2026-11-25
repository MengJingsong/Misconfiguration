#!/bin/bash
# usage: cluster-cell.sh <label> <mode flood|read> <k> <page>  -- one B3e cell (S4-A5), every command logged
set -u
T=/mydata/jingsong-cass-s4/o133/c509; H=/mydata/jingsong-cass-s4/o133/harness
L=$1; MODE=$2; K=$3; PAGE=$4; D=/mydata/jingsong-cass-s4/o133/cluster/run1/$L; mkdir -p $D
S=$D/session.txt; PID=$(cat $T/pid)
log(){ echo "### $(date -u +%FT%T.%3NZ) $(date +%s%3N) $*" >> $S; }
run(){ log "+ $*"; "$@" >> $S 2>&1; }
bs(){ $T/bin/nodetool -p 17199 sjk mx -mg -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesSent" -f Count 2>&1 | grep -Eo '^[0-9]+' | tail -1; }
log "cell $L mode=$MODE k=$K page=$PAGE pid=$PID"
run jcmd $PID GC.run
jcmd $PID GC.heap_info > $D/heapinfo-pre.txt 2>&1
run jcmd $PID VM.native_memory baseline
B0=$(bs); log "BytesSent pre=$B0"
$H/cluster-sampler.sh $PID $D/samples.txt & SP=$!
sleep 5
log "client start"
python3 $H/wm_client.py --port 19142 --mode $MODE --k $K --page $PAGE --hold 60 > $D/client.txt 2>&1 & CP=$!
if [ $MODE = flood ]; then
  until grep -q '^sent' $D/client.txt || ! kill -0 $CP 2>/dev/null; do sleep 0.5; done
  log "client: $(grep '^sent' $D/client.txt)"
  sleep 35
  log "end-of-hold readings start"
  jcmd $PID VM.native_memory summary.diff > $D/nmt-diff-endhold.txt 2>&1
  B1=$(bs); log "BytesSent endhold=$B1"
  ss -tmn 'sport = :19142' > $D/ss-server-endhold.txt; ss -tmn 'dport = :19142' > $D/ss-client-endhold.txt
  run jcmd $PID GC.run
  jcmd $PID GC.heap_info > $D/heapinfo-endhold.txt 2>&1
  log "end-of-hold readings done"
fi
wait $CP; log "client exit rc=$?: $(tail -2 $D/client.txt | tr '\n' ' ')"
[ $MODE = read ] && jcmd $PID VM.native_memory summary.diff > $D/nmt-diff-end.txt 2>&1
sleep 10
kill $SP; wait $SP 2>/dev/null
B2=$(bs); log "BytesSent post=$B2"
jcmd $PID GC.heap_info > $D/heapinfo-post.txt 2>&1
grep -c '^ERROR' $T/logs/system.log > $D/errors-count.txt 2>&1
log "cell done"
