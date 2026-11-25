#!/usr/bin/env bash
# o132: smoke test of the ClusterProbe fix (runbook defect 1) before the cluster tier restarts. Not part of the readings.
set -uo pipefail
W=${W:-/mydata/jingsong-cass-s4/o132}
exec > >(tee -a $W/logs/smoke.log) 2>&1
cd $W/src
CLASSPATH=$(cat $W/classpath.txt)
CJ="$(grep -hv '^\s*#' conf/jvm-clients.options conf/jvm11-clients.options | grep -v '^\s*$' | tr '\n' ' ') -XX:MaxDirectMemorySize=2g -Dio.netty.tryReflectionSetAccessible=true"
ulimit -n 100000 || true
cleanup() { [ -f $W/cassandra.pid ] && { p=$(cat $W/cassandra.pid); kill $p; for i in $(seq 1 120); do ps -p $p >/dev/null || break; sleep 1; done; ps -p $p >/dev/null && kill -9 $p; rm -f $W/cassandra.pid; }
            [ -f $W/proxy.pid ] && { kill $(cat $W/proxy.pid); rm -f $W/proxy.pid; }; rm -f $W/pause.flag; echo "smoke cleanup done"; }
trap cleanup EXIT
echo "=== smoke $(date)"
( export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary"; bin/cassandra -p $W/cassandra.pid > $W/logs/smoke-out.log 2>&1 )
for i in $(seq 1 120); do sleep 2; bin/nodetool statusbinary 2>/dev/null | grep -q running && break; done
bin/nodetool statusbinary
python3 $W/probe/pause-proxy.py 19042 9042 $W/pause.flag > $W/logs/smoke-proxy.log 2>&1 & echo $! > $W/proxy.pid; sleep 1
java $CJ -cp "$W/probe/classes:$CLASSPATH" ClusterProbe read 19042 4 4194304 7199 $W/pause.flag 2000 2>&1 | grep -E 'SAMPLE|RESULT|Exception|NullPointer' | head -20
echo "=== smoke done $(date)"
