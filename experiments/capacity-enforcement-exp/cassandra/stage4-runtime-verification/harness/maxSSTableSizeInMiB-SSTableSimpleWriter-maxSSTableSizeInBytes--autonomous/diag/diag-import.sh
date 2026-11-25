#!/bin/bash
# Diagnostic (not a reading): why did nodetool import find no SSTables? Logged; always stops the node.
S4=/mydata/jingsong-cass-s4/o117; C=$S4/cluster; SRC=$C/cassandra-5.0.9; NODE=$C/node
exec > >(tee -a $S4/logs/diag-import.log) 2>&1
set -x
cd $SRC; ulimit -n 100000; export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
J=$SRC/build/lib/jars/byteman-4.0.20.jar; JVM_EXTRA_OPTS="-javaagent:$J=script:$S4/harness/import-diag3.btm" bin/cassandra -p $NODE/cassandra.pid > $NODE/stdout3.log 2>&1
for i in $(seq 1 60); do [ -s $NODE/cassandra.pid ] && break; sleep 1; done
P=$(cat $NODE/cassandra.pid); echo $P > $NODE/started.pid
trap 'kill $P; for i in $(seq 1 90); do kill -0 $P 2>/dev/null || break; sleep 1; done; kill -9 $P 2>/dev/null; rm -f $NODE/started.pid; echo stopped' EXIT
for i in $(seq 1 120); do kill -0 $P || exit 1; bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(bin/nodetool statusbinary 2>/dev/null)" = running ] && break; sleep 3; done
bin/nodetool setlogginglevel org.apache.cassandra.db.SSTableImporter TRACE
bin/nodetool setlogginglevel org.apache.cassandra.db.Directories TRACE
bin/nodetool setlogginglevel org.apache.cassandra.db.lifecycle TRACE
bin/nodetool import --copy-data s4ks t_m16 $C/gen/out/t_m16/s4ks/t_m16; echo "rc=$?"
bin/nodetool tablestats s4ks.t_m16 | grep -E 'SSTable count'
ls -la $NODE/data/s4ks/
grep -n O117DIAG $NODE/stdout3.log | cut -c1-600 | head -40
