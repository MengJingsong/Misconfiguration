#!/bin/bash
# Cluster tier (B3e, with S4-A3) for o123, run on ms0604. Logs every command.
set -u
WORK=/mydata/jingsong-cass-s4/o123
C5=$WORK/cassandra-5.0.9
OUT=$WORK/run1/cluster-restart
mkdir -p $OUT
exec > >(tee -a $OUT/run-cluster.log) 2>&1
ts() { date -u +%FT%TZ; }
run() { echo "+ [$(ts)] $*"; "$@"; rc=$?; echo "  rc=$rc"; return $rc; }
PID=
stop_node() {
  if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
    echo "+ [$(ts)] kill $PID"; kill $PID
    for i in $(seq 1 120); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { echo "kill -9 $PID"; kill -9 $PID; sleep 2; }
  fi
  echo "+ [$(ts)] leftover check:"; ps -eo pid,cmd | grep -E '[C]assandraDaemon|[c]assandra-stress|[S]amplerCtl' | grep "$WORK" || echo "none under $WORK"
}
trap stop_node EXIT
cd $C5 || exit 1
cp $WORK/harness/SamplerCtl.java $WORK/SamplerCtl.java
run uname -m; run java -version
ulimit -n 100000; echo "ulimit -n = $(ulimit -n)"
if ss -ltn | grep -E ':(7000|7199|9042) '; then echo "PORTS BUSY"; exit 1; fi
echo "+ [$(ts)] start node"
MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $WORK/cassandra.pid > $WORK/start.log 2>&1
for i in $(seq 1 300); do
  [ -s $WORK/cassandra.pid ] && PID=$(cat $WORK/cassandra.pid)
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then echo "DAEMON DIED"; tail -30 logs/system.log; exit 1; fi
  if bin/nodetool status 2>/dev/null | grep -q '^UN' && bin/nodetool statusbinary 2>/dev/null | grep -q running; then break; fi
  sleep 2
done
echo "PID=$PID"; echo $PID > $OUT/pid
bin/nodetool status | grep '^UN' || { echo "NODE NOT UP"; exit 1; }
run jcmd $PID VM.flags | tr ' ' '\n' | grep -E 'MaxHeapSize|UseG1GC|UseParallelGC|UseConcMarkSweep'
echo "+ [$(ts)] warm-up stress (creates keyspace1.standard1)"
tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1 > $OUT/stress-warmup.out 2>&1; echo "  rc=$?"
grep -E 'Total partitions|Total errors' $OUT/stress-warmup.out
echo "+ [$(ts)] baseline histo"
jmap -histo:live $PID > $OUT/histo-baseline.txt; echo "  rc=$?"
echo "baseline count=$(hcount $OUT/histo-baseline.txt) live=$(htotal $OUT/histo-baseline.txt)"; grep 'Sampler\$Sample$' $OUT/histo-baseline.txt || echo "BASELINE: no Sampler\$Sample instances"
jcmd $PID GC.heap_info | tee $OUT/heapinfo-baseline.txt
echo "+ [$(ts)] nodetool profileload -s 2000 (expect rejection)"
bin/nodetool profileload keyspace1 standard1 1000 -s 2000 -a WRITE_SIZE > $OUT/profileload-s2000.txt 2>&1; echo "  rc=$?"
cat $OUT/profileload-s2000.txt
tpdrop() { v=$(bin/nodetool tpstats | awk '$1=="_SAMPLE"{print $2}'); [ -z "$v" ] && { echo "WARN no _SAMPLE row" >&2; v=0; }; echo $v; }
wcount() { bin/nodetool tablestats keyspace1.standard1 | awk -F: '/Local write count/{gsub(/ /,"",$2); print $2}'; }
used() { awk '/heap/ && /used/ {for(i=1;i<=NF;i++) if($i=="used"){v=$(i+1); gsub(/[^0-9]/,"",v); print v; exit}}' $1; }
hcount() { awk '$4=="org.apache.cassandra.metrics.Sampler$Sample"{print $2; f=1} END{if(!f) print 0}' $1; }
htotal() { awk '$1=="Total"{print $3}' $1; }
hbytes() { awk '$4=="org.apache.cassandra.metrics.Sampler$Sample"{print $3; f=1} END{if(!f) print 0}' $1; }
echo "C,W0,W1,D0,D1,S,count1,bytes1,usedK1,live1,count2,bytes2,usedK2,live2,deltaK,liveDelta,returned,stress_errors,stress_partitions,stress_secs" > $OUT/summary.csv
for C in 256 1024 100000 2000000; do
  echo "================ ARM C=$C [$(ts)]"
  D0=$(tpdrop); W0=$(wcount); echo "D0=$D0 W0=$W0"
  run java $WORK/SamplerCtl.java begin keyspace1 standard1 WRITE_SIZE $C 900000 || exit 1
  t0=$(date +%s)
  echo "+ [$(ts)] stress C=$C"
  tools/bin/cassandra-stress write n=1000000 no-warmup cl=ONE -pop seq=1..1000000 -rate threads=32 -node 127.0.0.1 -log file=$OUT/stress-$C.log > $OUT/stress-$C.out 2>&1; echo "  rc=$?"
  t1=$(date +%s)
  grep -E 'Total partitions|Total errors|Op rate' $OUT/stress-$C.out | head -5
  sleep 10
  D1=$(tpdrop); W1=$(wcount); echo "D1=$D1 W1=$W1"
  S=$(( (W1 - W0) - (D1 - D0) )); echo "S=$S"
  run bin/nodetool flush keyspace1 standard1
  echo "+ [$(ts)] M1"
  jmap -histo:live $PID > $OUT/histo-M1-$C.txt; jcmd $PID GC.heap_info > $OUT/heapinfo-M1-$C.txt
  grep 'Sampler\$Sample$\|^Total' $OUT/histo-M1-$C.txt; cat $OUT/heapinfo-M1-$C.txt
  RET=$(java $WORK/SamplerCtl.java finish keyspace1 standard1 WRITE_SIZE 10); echo "$RET"
  run java $WORK/SamplerCtl.java begin keyspace1 standard1 WRITE_SIZE 1 1
  sleep 2
  echo "+ [$(ts)] M2"
  jmap -histo:live $PID > $OUT/histo-M2-$C.txt; jcmd $PID GC.heap_info > $OUT/heapinfo-M2-$C.txt
  grep 'Sampler\$Sample$\|^Total' $OUT/histo-M2-$C.txt; cat $OUT/heapinfo-M2-$C.txt
  head -25 $OUT/histo-M1-$C.txt > $OUT/histo-M1-$C-top.txt
  run bin/cqlsh 127.0.0.1 -e "TRUNCATE keyspace1.standard1"
  c1=$(hcount $OUT/histo-M1-$C.txt); b1=$(hbytes $OUT/histo-M1-$C.txt); u1=$(used $OUT/heapinfo-M1-$C.txt)
  l1=$(htotal $OUT/histo-M1-$C.txt); l2=$(htotal $OUT/histo-M2-$C.txt)
  c2=$(hcount $OUT/histo-M2-$C.txt); b2=$(hbytes $OUT/histo-M2-$C.txt); u2=$(used $OUT/heapinfo-M2-$C.txt)
  se=$(awk -F: '/Total errors/{gsub(/ /,"",$2); split($2,a,"["); print a[1]}' $OUT/stress-$C.out | tr -d ,)
  sp=$(awk -F: '/Total partitions/{gsub(/ /,"",$2); split($2,a,"["); print a[1]}' $OUT/stress-$C.out | tr -d ,)
  echo "$C,$W0,$W1,$D0,$D1,$S,$c1,$b1,$u1,$l1,$c2,$b2,$u2,$l2,$((u1-u2)),$((l1-l2)),${RET#returned=},$se,$sp,$((t1-t0))" | tee -a $OUT/summary.csv
done
bin/nodetool tpstats > $OUT/tpstats-final.txt
cp logs/system.log $OUT/system.log 2>/dev/null; grep -c '^ERROR' logs/system.log
echo "+ [$(ts)] stop"
stop_node; PID=
echo DONE
