#!/bin/bash
# o125 cluster tier, one run (B3e steps 1-8, with S4-A1). Runs ON the node.
# usage: cluster-run.sh <run-name> <stock|1m|256m> <stall|nostall>
set -uo pipefail
R=$1; KNOB=$2; STALL=$3
WORK=/mydata/jingsong-cass-s4/o125
H=$WORK/harness
RUN=$WORK/runs/$R
CASS=$WORK/cass
mkdir -p $RUN
exec > >(tee -a $RUN/driver.log) 2>&1
set -x
case $KNOB in
  stock) MARKS="" ;;
  1m)    MARKS="-Dcassandra.test.flush_low_water_mark=524288 -Dcassandra.test.flush_high_water_mark=1048576" ;;
  256m)  MARKS="-Dcassandra.test.flush_low_water_mark=134217728 -Dcassandra.test.flush_high_water_mark=268435456" ;;
  *) echo bad knob; exit 1 ;;
esac
ulimit -n 100000
cleanup() {
  set +e
  [ -f $WORK/nodeB/pid ] && kill -CONT $(cat $WORK/nodeB/pid) 2>/dev/null
  pkill -u $(id -un) -f 'org.apache.cassandra.stress.Stress' 2>/dev/null
  pkill -u $(id -un) -f 'Sampler 7199' 2>/dev/null
  [ -n "${DG:-}" ] && kill $DG 2>/dev/null
  for X in A B; do [ -f $WORK/node$X/pid ] && kill $(cat $WORK/node$X/pid) 2>/dev/null; done
  for i in $(seq 1 60); do ps -eo cmd | grep -q '[C]assandraDaemon' || break; sleep 1; done
  ps -eo pid,cmd | grep -E '[C]assandraDaemon|[S]tress|[S]ampler 7199' && { echo "force kill"; for X in A B; do [ -f $WORK/node$X/pid ] && kill -9 $(cat $WORK/node$X/pid) 2>/dev/null; done; pkill -9 -u $(id -un) -f 'org.apache.cassandra.stress.Stress'; pkill -9 -u $(id -un) -f 'Sampler 7199'; }
  ps -eo pid,cmd | grep -E '[C]assandraDaemon|[S]tress|[S]ampler 7199' || echo "no CassandraDaemon/stress/sampler left"
  for i in $(seq 1 30); do ss -ltn | grep -qE ':(7000|9042|7199|7299) ' || break; sleep 2; done; ss -ltn | grep -E ':(7000|9042|7199|7299) ' || echo "ports free"
}
trap cleanup EXIT
date -u; df -h /mydata
ps -eo pid,cmd | grep '[C]assandraDaemon' && { echo "a CassandraDaemon is already running"; exit 1; }
# defect fix #4: the previous run's listeners can outlive its ps entry for a moment; wait up to 90 s
for i in $(seq 1 30); do ss -ltn | grep -qE '127\.0\.0\.[12]:(7000|9042|7199|7299) |:7199 |:7299 ' || break; sleep 3; done
ss -ltn | grep -E '127\.0\.0\.[12]:(7000|9042|7199|7299) |:7199 |:7299 ' && { echo "ports busy"; exit 1; }
# step 1
rm -rf $WORK/nodeA $WORK/nodeB; mkdir -p $WORK/nodeA/logs $WORK/nodeB/logs
# step 2 (defect fix #3: start A, the seed, first; then B; B started first died waiting for the seed's schema)
startnode() { # $1 = A|B
  local X=$1 EXTRA=""
  [ $X = A ] && EXTRA="-XX:MaxDirectMemorySize=1G -XX:NativeMemoryTracking=summary $MARKS"
  CASSANDRA_CONF=$WORK/conf$X CASSANDRA_LOG_DIR=$WORK/node$X/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$EXTRA" $CASS/bin/cassandra -p $WORK/node$X/pid > $RUN/start$X.out 2>&1
}
waitup() { # $1 = number of UN nodes wanted; $2.. = nodes whose binary must run
  local want=$1; shift; local ok=0 i n X P b good
  for i in $(seq 1 90); do
    sleep 4
    for X in A B; do [ -f $WORK/node$X/pid ] && { pgrep -F $WORK/node$X/pid >/dev/null || { echo "$X died"; tail -30 $WORK/node$X/logs/system.log; return 1; }; }; done
    n=$(CASSANDRA_CONF=$WORK/confA $CASS/bin/nodetool -p 7199 status 2>/dev/null | grep -c '^UN')
    good=1
    for X in "$@"; do if [ $X = A ]; then P=7199; else P=7299; fi
      b=$(CASSANDRA_CONF=$WORK/conf$X $CASS/bin/nodetool -p $P statusbinary 2>/dev/null); [ "$b" = running ] || good=0; done
    if [ "$n" = "$want" ] && [ $good = 1 ]; then ok=1; break; fi
  done
  [ $ok = 1 ]
}
startnode A
waitup 1 A || { echo "A did not come up"; exit 1; }
startnode B
waitup 2 A B || { echo "cluster did not come up"; exit 1; }
ok=1
[ $ok = 1 ] || { echo "cluster did not come up"; exit 1; }
CASSANDRA_CONF=$WORK/confA $CASS/bin/nodetool -p 7199 status
# step 3
jcmd $(cat $WORK/nodeA/pid) VM.system_properties | grep flush_ > $RUN/props.txt; echo "props:"; cat $RUN/props.txt
echo "$KNOB $STALL" > $RUN/knob.txt
[ -f $WORK/sampler/Sampler.class ] || { mkdir -p $WORK/sampler && javac -d $WORK/sampler $H/Sampler.java || exit 1; }
# step 4
T0=$(date +%s); echo $T0 > $RUN/t0
CASSANDRA_CONF=$WORK/confA $CASS/tools/bin/cassandra-stress write duration=120s cl=ONE no-warmup -schema "replication(strategy=SimpleStrategy,factor=2)" -col "n=FIXED(1)" "size=FIXED(1024)" -rate threads=32 -node whitelist 127.0.0.1 -log level=minimal > $RUN/stress.log 2>&1 &
SP=$!
# S4-A4(b) disk guard: abort the run (runbook defect) if /mydata free < 3 GiB
( while kill -0 $SP 2>/dev/null; do a=$(df --output=avail -k /mydata | tail -1); if [ $a -lt 3145728 ]; then echo "DISK ABORT avail=${a}KB $(date +%s%3N)" > $RUN/ABORT_DISK; pkill -u $(id -un) -f 'org.apache.cassandra.stress.Stress'; break; fi; sleep 5; done ) &
DG=$!
at() { local now=$(date +%s); local d=$(( T0 + $1 - now )); [ $d -gt 0 ] && sleep $d; }
# step 5
# defect fix #5: on the loaded m400 the single-file launch at t = 20 s gave its first sample only at STOP (no baseline).
# Precompiled Sampler, started at t = 5 s with 210 samples (covers t = 5..110 s as before t = 20..110 s); window and baseline unchanged.
at 5; java -cp $WORK/sampler Sampler 7199 127.0.0.2_7000 210 > $RUN/samples.csv 2> $RUN/sampler.err &
SAMP=$!
# step 6
at 40
if [ $STALL = stall ]; then kill -STOP $(cat $WORK/nodeB/pid); fi
date +%s%3N > $RUN/stop.ts
F1=$(sed -n 2p $RUN/samples.csv | cut -d, -f1); ST=$(cat $RUN/stop.ts)
if [ -z "$F1" ] || [ $F1 -gt $(( ST - 10000 )) ]; then echo "SAMPLER LATE first=$F1 stop=$ST: no 10 s baseline"; touch $RUN/SAMPLER_LATE; exit 3; fi
echo "sampler first sample $(( (ST - F1) / 1000 )) s before STOP"
at 55; jcmd $(cat $WORK/nodeA/pid) VM.native_memory summary > $RUN/nmt.txt 2>&1
at 60
if [ $STALL = stall ]; then kill -CONT $(cat $WORK/nodeB/pid); fi
date +%s%3N > $RUN/cont.ts
# step 7
wait $SP; echo "stress exit $?"
wait $SAMP; echo "sampler exit $?"
cp $WORK/nodeA/logs/system.log $RUN/systemA.log; cp $WORK/nodeB/logs/system.log $RUN/systemB.log
grep -E 'is now (DOWN|UP)' $RUN/systemA.log
sed -n '/^Results:/,$p' $RUN/stress.log | head -30
grep -m3 -E 'Total errors|Op rate' $RUN/stress.log
wc -l $RUN/samples.csv; head -2 $RUN/samples.csv; cat $RUN/sampler.err | head -5
df -h /mydata; du -sh $WORK/nodeA $WORK/nodeB
[ -f $RUN/ABORT_DISK ] && { cat $RUN/ABORT_DISK; exit 2; }
# step 8 in cleanup (trap)
date -u
