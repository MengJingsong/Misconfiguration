#!/usr/bin/env bash
# Build the B13 data template once (not a reading): base build, heap 2 GiB, direct auto; schema + 64 x 56 x 64 KiB over v4;
# flush, drain, stop; node/data -> tmpl/data.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); ROOT=/mydata/s4/b13-w3; NODE=$ROOT/node
export BUILD=base XMX=2048M DIRECT=auto DUMP=0
"$H/ctl.sh" gen && "$H/ctl.sh" start || exit 1
for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && break; sleep 2; done
grep -q "Starting listening for CQL clients" $NODE/logs/system.log || { echo "START FAIL"; "$H/ctl.sh" stop; exit 1; }
"$H/jv.sh" load 127.0.0.131 || { echo "LOAD FAIL"; "$H/ctl.sh" stop; exit 1; }
NT=/mydata/s4/cassandra-base/bin/nodetool
CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 flush b13 && CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 tablestats b13.t | grep -E "SSTable count|Space used \(live\)|Number of partitions"
CASSANDRA_CONF=$NODE/conf $NT -h 127.0.0.1 -p 7313 drain
"$H/ctl.sh" stop
rm -rf $ROOT/tmpl; mkdir -p $ROOT/tmpl; cp -a $NODE/data $ROOT/tmpl/data; du -sh $ROOT/tmpl/data
grep -m1 "Global buffer pool limit" $NODE/logs/system.log
echo TMPL DONE
