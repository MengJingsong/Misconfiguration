#!/bin/bash
# Case B3e (with amendments A1, A4, A5). usage: cluster-run.sh <v> <PARTS> <ROWS> <VSIZE> <K> <label>
set -uo pipefail
V=$1; PARTS=$2; ROWS=$3; VSIZE=$4; K=$5; LABEL=$6
W=/mydata/jingsong-cass-s4/o120; H=$W/harness; B=$W/s3probe/$V; N=$W/s3node/$LABEL; O=$W/run1/cluster-$LABEL
mkdir -p $O
exec > >(tee -a $O/run.log) 2>&1
log(){ echo "[$(date +%s%3N) $(date '+%F %T %Z')] $*"; }
run(){ log "+ $*"; "$@"; local rc=$?; [ $rc -eq 0 ] || log "rc=$rc"; return $rc; }
NT=$B/bin/nodetool
# harness defect H1 (2026-11-25): started as bin/cassandra from $B, the command line holds relative paths, so
# match the absolute log dir (-Dcassandra.logdir=$N/logs) or the pid file instead of "$B/".
daemon(){ local p; p=$(cat $N/pid 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "$p pidfile"; return 0; fi
          ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -F -- "$N/logs" | cut -c1-80 | grep . ; }
stop_node(){
  if daemon >/dev/null; then
    log "+ $NT stopdaemon"; $NT stopdaemon || true
    for i in $(seq 60); do daemon >/dev/null || break; sleep 2; done
    if daemon >/dev/null; then log "stopdaemon did not stop it; kill"; P=$(daemon | awk '{print $1}'); kill $P 2>/dev/null; sleep 10; daemon >/dev/null && kill -9 $P; fi
  fi
  log "daemon check after stop: $(daemon || echo none)"
}
cleanup(){
  if daemon >/dev/null; then log "REFUSING cleanup: daemon still alive: $(daemon)"; return 1; fi
  [ -f $N/logs/system.log ] && cp $N/logs/system.log $O/system.log
  [ -f $N/logs/debug.log ] && grep -E 'DiskAccessMode|Compact|compaction' $N/logs/debug.log | tail -200 > $O/debug-excerpt.log || true
  log "+ rm -rf $N (data, commitlog, hints, caches; logs copied to $O)"
  rm -rf $N
  log "disk: $(df -h /mydata | tail -1)"
}
fail(){ log "FAIL: $*"; kill $CPID 2>/dev/null; stop_node; cleanup; exit 1; }
CPID=
sample(){ # one sample: the three MBeans in parallel, epoch second; phase tag
  local phase=$1 ts=$(date +%s)
  $NT sjk mx -mg -b "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=UsedSize" -f Value > $O/.s1 2>&1 & local p1=$!
  $NT sjk mx -mg -b "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=OverflowSize" -f Value > $O/.s2 2>&1 & local p2=$!
  $NT sjk mx -mg -b "java.nio:type=BufferPool,name=direct" -f MemoryUsed > $O/.s3 2>&1 & local p3=$!
  local cs=""
  if [ "$phase" = during ]; then $NT compactionstats > $O/.cs 2>&1; fi
  wait $p1 $p2 $p3   # harness defect H2: a bare wait also waits for the tee process substitution (bash >= 5.1)
  echo "$ts $phase UsedSize $(tail -1 $O/.s1)" >> $O/$phase.txt
  echo "$ts $phase OverflowSize $(tail -1 $O/.s2)" >> $O/$phase.txt
  echo "$ts $phase DirectMemoryUsed $(tail -1 $O/.s3)" >> $O/$phase.txt
  if [ "$phase" = during ]; then
    if grep -qE 'Compaction[[:space:]]+p[[:space:]]+t' $O/.cs; then c=yes; else c=no; fi
    echo "$ts during COMPACTING $c" >> $O/during.txt
    { echo "== $ts"; cat $O/.cs; } >> $O/compactionstats.txt
  fi
}

log "cluster-run $V PARTS=$PARTS ROWS=$ROWS VSIZE=$VSIZE K=$K label=$LABEL on $(hostname) $(uname -m)"
run grep -n "MAX_BUFFER_SIZE =" $B/src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
# step 0: ports and no other daemon
if ss -ltn | grep -E ':(7000|7199|9042|9091) '; then log "FAIL: ports busy"; exit 1; fi
if ps -eo cmd | grep '[C]assandraDaemon'; then log "FAIL: a CassandraDaemon is already running"; exit 1; fi
# step 1
run mkdir -p $N/data $N/commitlog $N/saved_caches $N/hints $N/logs
[ -f $B/conf/cassandra.yaml.orig ] || run cp $B/conf/cassandra.yaml $B/conf/cassandra.yaml.orig
run python3 -I $H/mkyaml.py $B/conf/cassandra.yaml.orig $B/conf/cassandra.yaml $N || fail mkyaml
cp $B/conf/cassandra.yaml $O/cassandra.yaml
# step 2
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
cd $B
log "+ CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $N/pid"
CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $N/pid > $O/cassandra-start.out 2>&1
sleep 3; log "daemon after launch: $(daemon || echo NOT-FOUND)"
up=no
for i in $(seq 90); do
  sleep 2
  daemon >/dev/null || fail "daemon died during start"
  if $NT status 2>/dev/null | grep -q '^UN' && $NT statusbinary 2>/dev/null | grep -q running; then up=yes; break; fi
done
[ $up = yes ] || fail "node not up in 180 s"
run $NT status
run grep -E 'DiskAccessMode|disk_optimization_strategy|file_cache_enabled' $N/logs/system.log | head -5
grep -q 'DiskAccessMode is standard, indexAccessMode is mmap' $N/logs/system.log || fail "access mode not standard/mmap"
# step 3
run bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE p WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE p.t (pk text, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'} AND compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};" || fail cqlsh
run bin/cqlsh 127.0.0.1 -e "DESCRIBE TABLE p.t" | grep -E "compression|compaction" 
run $NT disableautocompaction p t || fail disableautocompaction
# step 4
t0=$(date +%s)
run python3 -I $H/load.py $V $K $PARTS $ROWS $VSIZE > $O/load.log 2>&1 || { tail -20 $O/load.log; fail load; }
log "load took $(( $(date +%s) - t0 )) s"; tail -2 $O/load.log
run $NT tablestats p.t > $O/tablestats-before.txt
cnt=$(grep "SSTable count" $O/tablestats-before.txt | head -1 | awk '{print $NF}')
log "SSTable count = $cnt (expect $K)"
[ "$cnt" = "$K" ] || fail "SSTable count $cnt != $K"
d1=$(ls $N/data/p/t-*/*-Data.db | head -1)
run tools/bin/sstablemetadata $d1 > $O/sstablemetadata.txt 2>&1
grep -iE 'partition size|Compression|percentile|^ *[0-9]+ ' $O/sstablemetadata.txt | head -60 > $O/sstablemetadata-excerpt.txt
ls -l $N/data/p/t-*/*-Data.db > $O/datafiles.txt
# step 5 baseline
log "baseline: 12 samples"
for i in $(seq 12); do sample base; sleep 5; done
# step 6
run $NT setcompactionthroughput 1
run $NT getcompactionthroughput
log "+ $NT compact p t &"
$NT compact p t > $O/compact.out 2>&1 & CPID=$!
sleep 20
run $NT compactionstats | tee $O/compactionstats-t20.txt
grep -qE 'Compaction[[:space:]]+p[[:space:]]+t' $O/compactionstats-t20.txt || log "WARNING: compaction of p.t not listed at t+20 s"
log "during: 120 s"
tend=$(( $(date +%s) + 120 ))
while [ $(date +%s) -lt $tend ]; do sample during; sleep 5; done
# step 7
run $NT stop COMPACTION
for i in $(seq 60); do kill -0 $CPID 2>/dev/null || break; sleep 2; done
kill -0 $CPID 2>/dev/null && { log "nodetool compact still running; kill"; kill $CPID; }
log "compact client output:"; tail -5 $O/compact.out
log "after: 6 samples"
for i in $(seq 6); do sample after; sleep 5; done
run $NT tablestats p.t > $O/tablestats-after.txt
grep "SSTable count" $O/tablestats-after.txt | head -1
grep -E 'Compacted|CompactionTask|Compaction interrupted|Stopped' $N/logs/system.log | tail -10 > $O/system-compaction-excerpt.log
# step 8
stop_node
cleanup || { log "FAIL: cleanup refused"; exit 1; }
rm -f $O/.s1 $O/.s2 $O/.s3 $O/.cs
log "CLUSTER-RUN-OK $LABEL"
