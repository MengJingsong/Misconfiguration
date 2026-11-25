#!/bin/bash
# Stage-4 cluster tier (B3e) for order 96, on the run node. Usage:
#   cluster-run.sh shake            # instrument check on a throwaway node dir (no readings)
#   cluster-run.sh main             # B3e steps 1-6 and 8 on $W/node (stock)
#   cluster-run.sh pc100            # optional step 7: patched jar ($W/unit), cap=100, steps 2-4
# Every command and its output goes to $OUT/command.log; the run stops at the first failed step.
set -uo pipefail
W=/mydata/jingsong-cass-s4/o96
MODE=${1:?mode}
case $MODE in
  shake) N=$W/shake-node; D=$W/shake-data; OUT=$W/raw/cluster-shake ;;
  main)  N=$W/node;       D=$W/cdata;      OUT=$W/raw/cluster ;;
  pc100) N=$W/unit;       D=$W/cdata-pc100; OUT=$W/raw/cluster-pc100 ;;
esac
CQL=$W/cql
PIDF=$W/cassandra-$MODE.pid
mkdir -p $OUT $CQL
exec > >(tee -a $OUT/command.log) 2>&1
say() { echo "[$(date -u +%FT%TZ) $(date +%s%3N)] $*"; }
die() { say "!!! STOP: $*"; stop_node; exit 1; }
x() { say "+ $*"; "$@"; }
nt() { $N/bin/nodetool -h 127.0.0.1 "$@"; }
cq() { $N/bin/cqlsh 127.0.0.1 --request-timeout=120 "$@"; }

stop_node() {
  local p=$(cat $PIDF 2>/dev/null)
  if [ -n "$p" ] && kill -0 $p 2>/dev/null; then
    say "stopping CassandraDaemon pid $p"; kill $p
    for i in $(seq 1 60); do kill -0 $p 2>/dev/null || break; sleep 1; done
    kill -0 $p 2>/dev/null && { say "kill -9 $p"; kill -9 $p; }
  fi
  ps -eo pid,cmd | grep '[C]assandraDaemon' | grep "$N/" && say "WARNING: daemon still present" || say "no CassandraDaemon from $N left"
}

start_node() {
  for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && die "port $p busy"; done
  rm -rf $D; mkdir -p $D
  x python3 $W/harness/mkyaml.py $N $D || die mkyaml
  ulimit -n 100000
  export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M
  if [ $MODE = pc100 ]; then
    say "+ JVM_EXTRA_OPTS=-Dcassandra.test.codec_cache_max_weight=100 bin/cassandra -p $PIDF"
    ( cd $N && JVM_EXTRA_OPTS="-Dcassandra.test.codec_cache_max_weight=100" bin/cassandra -p $PIDF > $OUT/cassandra-start.out 2>&1 )
  else
    say "+ bin/cassandra -p $PIDF"
    ( cd $N && bin/cassandra -p $PIDF > $OUT/cassandra-start.out 2>&1 )
  fi
  sleep 3
  for i in $(seq 1 120); do
    [ -f $PIDF ] && kill -0 $(cat $PIDF) 2>/dev/null || die "daemon died during start"
    if nt status 2>/dev/null | grep -q '^UN' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then say "node UN and binary running (pid $(cat $PIDF))"; break; fi
    sleep 2
  done
  [ "$(nt statusbinary 2>/dev/null)" = running ] || die "node not up after 240 s"
  ps -o pid,cmd -p $(cat $PIDF) | tail -1 | tr ' ' '\n' | grep -E 'Xmx|Xms|Xmn|codec_cache|UseG1' | tr '\n' ' '; echo
}

fcount() { cq -e "SELECT count(*) FROM system_schema.functions WHERE keyspace_name='ks';" 2>&1 | awk 'NF==1 && $1 ~ /^[0-9]+$/{print $1}'; }

sample() {   # sample <tag>: 3 samples, 30 s apart (S4-A7)
  local tag=$1 pid=$(cat $PIDF)
  for n in 1 2 3; do
    say "sample $tag/$n"
    jcmd $pid GC.class_histogram > $OUT/h_${tag}_$n.txt 2>&1
    jcmd $pid GC.run > /dev/null 2>&1; sleep 5
    jcmd $pid GC.heap_info > $OUT/hi_${tag}_$n.txt 2>&1
    nt info > $OUT/ni_${tag}_$n.txt 2>&1
    local wsvr=$(awk '$4=="com.google.common.cache.LocalCache$WeightedStrongValueReference"{print $2}' $OUT/h_${tag}_$n.txt)
    local svr=$(awk '$4=="com.google.common.cache.LocalCache$StrongValueReference"{print $2}' $OUT/h_${tag}_$n.txt)
    local ckey=$(awk '$4=="org.apache.cassandra.cql3.functions.types.CodecRegistry$CacheKey"{print $2}' $OUT/h_${tag}_$n.txt)
    local vec=$(awk '$4=="org.apache.cassandra.cql3.functions.types.VectorCodec$FixedLength"{print $2}' $OUT/h_${tag}_$n.txt)
    local tup=$(awk '$4=="org.apache.cassandra.cql3.functions.types.TypeCodec$TupleCodec"{print $2}' $OUT/h_${tag}_$n.txt)
    local tt=$(awk '$4=="org.apache.cassandra.cql3.functions.types.TupleType"{print $2}' $OUT/h_${tag}_$n.txt)
    local obj=$(awk '$4=="[Ljava.lang.Object;"{print $3}' $OUT/h_${tag}_$n.txt)
    local tot=$(awk '$1=="Total"{print $3}' $OUT/h_${tag}_$n.txt)
    local used=$(grep -o 'garbage-first heap.*used [0-9]*K' $OUT/hi_${tag}_$n.txt | grep -o 'used [0-9]*K' | grep -o '[0-9]*')
    local nih=$(grep -i '^Heap Memory' $OUT/ni_${tag}_$n.txt | sed 's/  */ /g')
    echo "READING tag=$tag n=$n epoch_ms=$(date +%s%3N) CacheKey=${ckey:-0} SVR=${svr:-0} WSVR=${wsvr:-0} VectorCodecFixed=${vec:-0} TupleCodec=${tup:-0} TupleType=${tt:-0} ObjArrBytes=${obj:-0} HistTotalBytes=${tot:-0} HeapUsedAfterGC_K=${used:-NA} | $nih" | tee -a $OUT/readings.txt
    [ $n -lt 3 ] && sleep 30
  done
  local fc=$(fcount); echo "READING tag=$tag functions=$fc" | tee -a $OUT/readings.txt
}

apply() {   # apply <cql file> <tag>
  local f=$1 tag=$2 t0=$(date +%s)
  say "+ cqlsh -f $f"
  cq -f $CQL/$f > $OUT/cqlsh_$tag.out 2> $OUT/cqlsh_$tag.err
  local rc=$? errs=$(grep -c -iE 'error|exception' $OUT/cqlsh_$tag.err)
  say "cqlsh $f rc=$rc error_lines=$errs seconds=$(( $(date +%s) - t0 ))"
  echo "TIMING tag=$tag file=$f seconds=$(( $(date +%s) - t0 )) cqlsh_rc=$rc error_lines=$errs" >> $OUT/readings.txt
  [ $errs -gt 0 ] && head -5 $OUT/cqlsh_$tag.err
  kill -0 $(cat $PIDF) 2>/dev/null || die "daemon died during $f"
}

say "=== cluster-run $MODE start host=$(hostname) arch=$(uname -m)"
x python3 $W/harness/gen-cql.py $CQL || die gen-cql
if [ $MODE = shake ]; then
  rm -rf $N; x cp -a /mydata/s4/cassandra-base $N
  start_node
  t0=$(date +%s%3N); cq -f $CQL/shake.cql 2>&1 | tail -5; say "shake.cql took $(( $(date +%s%3N) - t0 )) ms"
  cq -e "SELECT function_name, argument_types FROM system_schema.functions WHERE keyspace_name='ks';" 2>&1 | cut -c1-160
  jcmd $(cat $PIDF) GC.class_histogram | grep -E 'CodecRegistry\$CacheKey|StrongValueReference|VectorCodec\$FixedLength|TypeCodec\$TupleCodec|functions.types.TupleType|^Total'
  stop_node; rm -rf $N $D; say "=== shake done"; exit 0
fi

start_node
sample base
x cq -e "CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1};" || die keyspace
apply narrow_1_500.cql n500;       sample n500
apply narrow_501_2000.cql n2000;   sample n2000
apply narrow_2001_4000.cql n4000; sample n4000
apply narrow_drop.cql ndrop;       sample ndrop
if [ $MODE = main ]; then
  apply wide_m1.cql w1;            sample w1
  apply wide_m1_drop.cql w1drop;   sample w1drop
  apply wide_m2000.cql w2000;      sample w2000
  apply wide_m2000_drop.cql w2000drop; sample w2000drop
fi
grep -c '^ERROR' $N/logs/system.log | sed 's/^/system.log ERROR lines: /'
grep '^ERROR\|OutOfMemory' $N/logs/system.log | head -5
du -sh $D
stop_node
cp $N/logs/system.log $OUT/system.log 2>/dev/null; gzip -f $OUT/system.log
cp $N/logs/gc.log* $OUT/ 2>/dev/null
say "=== cluster-run $MODE end"
