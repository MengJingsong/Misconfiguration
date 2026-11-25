#!/bin/bash
# o124 cluster tier driver (B3e). Logs every command. WORK must be set. Stops at the first failed check.
set -u
: "${WORK:?}"
SRC=$WORK/src; cd $SRC || exit 1
FE=src/java/org/apache/cassandra/net/FrameEncoder.java
T=org.apache.cassandra.transport.FrameMaxSizeProbeTest
JAR=$SRC/build/apache-cassandra-5.0.9-SNAPSHOT.jar
export PYTHONPATH=$SRC/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0
for z in pure_sasl-0.6.2-py2-none-any wcwidth-0.2.5-py2.py3-none-any pyasyncore-1.0.5-py3-none-any geomet-0.1.0; do PYTHONPATH=$PYTHONPATH:$SRC/lib/$z.zip; done
export PYTHONPATH
log(){ echo "+ [$(date +%s%3N)] $*"; }
die(){ echo "FATAL: $*"; stop_all; exit 3; }
nt(){ $SRC/bin/nodetool "$@" 2>&1; }
start_node(){ # $1 tag
  rm -f $WORK/pause $WORK/node.pid $WORK/cassandra.pid
  ss -ltn | grep -E ':(9042|7000|7199|19042) ' && die "port busy before start"
  log "start node ($1)"
  ( ulimit -n 100000; MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary" \
      $SRC/bin/cassandra -p $WORK/cassandra.pid > $WORK/logs/node-$1.out 2>&1 )
  for i in $(seq 1 120); do
    sleep 2
    [ -s $WORK/cassandra.pid ] && ! kill -0 $(cat $WORK/cassandra.pid) 2>/dev/null && die "daemon died during start"
    if nt status | grep -q '^UN' && nt statusbinary | grep -q running; then cp $WORK/cassandra.pid $WORK/node.pid; log "node up after $((i*2)) s, pid $(cat $WORK/node.pid)"; break; fi
  done
  nt statusbinary | grep -q running || die "node did not come up"
  [ -s $WORK/node.pid ] || die "no node.pid"
  log "start proxy"; python3 $WORK/proxy.py $WORK/pause > $WORK/logs/proxy-$1.log 2>&1 & echo $! > $WORK/proxy.pid
  sleep 1; kill -0 $(cat $WORK/proxy.pid) || die "proxy died"
  grep 'Global buffer pool limit' $SRC/logs/system.log | tail -1
}
stop_all(){
  # defect D2 fix (2026-11-25): the JVM deletes the pidfile (deleteOnExit) at the START of shutdown, so the pid is
  # read once, at start, into $WORK/node.pid, and the wait loop uses that copy.
  rm -f $WORK/pause
  if [ -s $WORK/node.pid ] && kill -0 $(cat $WORK/node.pid) 2>/dev/null; then
    NP=$(cat $WORK/node.pid); log "stop node pid $NP"; kill $NP
    for i in $(seq 1 90); do kill -0 $NP 2>/dev/null || break; sleep 1; done
    kill -0 $NP 2>/dev/null && { log "node still alive after 90 s: kill -9"; kill -9 $NP; }
    log "node $NP exited"
  fi
  if [ -s $WORK/proxy.pid ] && kill -0 $(cat $WORK/proxy.pid) 2>/dev/null; then log "stop proxy"; kill $(cat $WORK/proxy.pid); fi
  sleep 1
  ps -eo pid,cmd | grep -E '[C]assandraDaemon|[p]roxy.py' | cut -c1-120 || log "no CassandraDaemon / proxy left"
  ss -ltn | grep -E ':(9042|7000|7199|19042) ' || log "ports 9042/7000/7199/19042 free"
}
probe(){ # $1 K $2 outfile
  log "probe K=$1 -> $2"; python3 $WORK/probe.py probe $1 2>&1 | tee $WORK/$2
  grep -q 'result sizes' $WORK/$2 || die "probe $2 failed"
  ss -tn '( sport = :9042 )' | tee -a $WORK/$2.conns
}
rebuild(){ # $1 tag
  log "sed -n 41p"; sed -n 41p $FE
  log "ant clean jar ($1)"; ( time ant clean jar </dev/null ) > $WORK/logs/cluster-build-$1.log 2>&1; tail -4 $WORK/logs/cluster-build-$1.log
  grep -q 'BUILD SUCCESSFUL' $WORK/logs/cluster-build-$1.log || die "build $1 failed"
  log "stale-build check: javap jar"; javap -c -p -constants -cp $JAR org.apache.cassandra.transport.Flusher | grep -A8 'static {}' | tee $WORK/cluster-buildcheck-$1.javap
  log "stale-build check: B2 test"; ant testsome -Dtest.name=$T </dev/null > $WORK/logs/cluster-buildcheck-$1-testsome.log 2>&1
  $WORK/harness/extract-probe.sh $WORK/logs/cluster-buildcheck-$1-testsome.log | grep . | tee $WORK/cluster-buildcheck-$1.txt
}
trap 'stop_all' EXIT
cp $WORK/harness/proxy.py $WORK/harness/probe.py $WORK/harness/sample.sh $WORK/; chmod +x $WORK/sample.sh
log "yaml: networking_cache_size 128MiB"; sed -i 's/^# networking_cache_size: 128MiB/networking_cache_size: 128MiB/' conf/cassandra.yaml; grep -n '^networking_cache_size' conf/cassandra.yaml || die "yaml edit"
log "jar check M17"; sed -n 41p $FE; javap -c -p -constants -cp $JAR org.apache.cassandra.transport.Flusher | grep -A8 'static {}' | tee $WORK/cluster-buildcheck-M17.javap
log "tcp buffers"; sysctl net.ipv4.tcp_wmem net.ipv4.tcp_rmem
# step 4: M17 K=8
start_node M17
log "setup data"; python3 $WORK/probe.py setup 8 2>&1 | tail -3; nt flush o124; du -sh $SRC/data/data/o124
probe 8 cluster-M17-K8.txt
# step 5: K=4
probe 4 cluster-M17-K4.txt
# step 6
stop_all
# step 7: positive control
log "yaml: networking_cache_size 16MiB"; sed -i 's/^networking_cache_size: 128MiB/networking_cache_size: 16MiB/' conf/cassandra.yaml; grep -n '^networking_cache_size' conf/cassandra.yaml
start_node M17-cache16
probe 8 cluster-M17-cache16.txt
stop_all
sed -i 's/^networking_cache_size: 16MiB/networking_cache_size: 128MiB/' conf/cassandra.yaml; grep -n '^networking_cache_size' conf/cassandra.yaml
# step 8: M16
sed -i '41s/1 << 17/1 << 16/' $FE; rebuild M16
start_node M16; probe 8 cluster-M16-K8.txt; stop_all
# step 9: M15
sed -i '41s/1 << 16/1 << 15/' $FE; rebuild M15
start_node M15; probe 8 cluster-M15-K8.txt; stop_all
cp $SRC/logs/system.log $WORK/logs/system-last.log
log "cluster done"
