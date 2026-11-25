#!/usr/bin/env bash
# o114 B3e step 4 (optional validity check), S4-A1 paths; node stopped by nodetool, then by PID if needed.
set -x
export WORK=/mydata/jingsong-cass-s4/o114; R=$WORK/probe/run.sh; S=$WORK/src
date -u +%FT%TZ
KEEP=1 HEAPOPTS="-Xmx2g" $R p-m3 unsorted 16 524288 1024 0 insert m3
rm -rf $WORK/node; mkdir -p $WORK/node/conf $WORK/node/logs
cp -a $S/conf/. $WORK/node/conf/
Y=$WORK/node/conf/cassandra.yaml
python3 - "$Y" "$WORK/node" <<'PY'
import sys,re
y,n=sys.argv[1],sys.argv[2]
s=open(y).read()
s=re.sub(r'(?m)^# data_file_directories:\n#     - /var/lib/cassandra/data', 'data_file_directories:\n    - %s/data'%n, s)
s=re.sub(r'(?m)^# commitlog_directory:.*$', 'commitlog_directory: %s/commitlog'%n, s)
s=re.sub(r'(?m)^# hints_directory:.*$', 'hints_directory: %s/hints'%n, s)
s=re.sub(r'(?m)^# saved_caches_directory:.*$', 'saved_caches_directory: %s/saved_caches'%n, s)
s=re.sub(r'(?m)^# cdc_raw_directory:.*$', 'cdc_raw_directory: %s/cdc_raw'%n, s)
s=re.sub(r'(?m)^range_request_timeout:.*$', 'range_request_timeout: 120000ms', s)
s=re.sub(r'(?m)^read_request_timeout:.*$', 'read_request_timeout: 120000ms', s)
s += '\n# D1 (2026-11-25): 5.0 bounds a whole native request by native_transport_timeout (default 12s)\nnative_transport_timeout: 600s\n'
open(y,'w').write(s)
PY
grep -nE '^(data_file_directories|    - /mydata|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|range_request_timeout|read_request_timeout|native_transport_timeout|partitioner)' $Y
ulimit -n 100000
CASSANDRA_CONF=$WORK/node/conf CASSANDRA_LOG_DIR=$WORK/node/logs $S/bin/cassandra -p $WORK/node/pid > $WORK/node/logs/start.out 2>&1
sleep 2; cat $WORK/node/pid; echo
ok=0
for i in $(seq 1 90); do
  pgrep -f CassandraDaemon >/dev/null || { echo "daemon died"; break; }
  if CASSANDRA_CONF=$WORK/node/conf $S/bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$(CASSANDRA_CONF=$WORK/node/conf $S/bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
echo "node_up=$ok"
if [ $ok = 1 ]; then
  CASSANDRA_CONF=$WORK/node/conf $S/bin/nodetool status
  $S/bin/cqlsh -e "CREATE KEYSPACE probe WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression={'enabled':'false'};"
  CASSANDRA_CONF=$WORK/node/conf $S/bin/sstableloader -d 127.0.0.1 $WORK/out/p-m3/probe/t > $WORK/logs/p-m3-loader.log 2>&1; echo "loader_exit=$?"
  tail -5 $WORK/logs/p-m3-loader.log
  $S/bin/cqlsh --request-timeout=600 -e "SELECT count(*) FROM probe.t"
  CASSANDRA_CONF=$WORK/node/conf $S/bin/nodetool stopdaemon
fi
for i in $(seq 1 30); do pgrep -f CassandraDaemon >/dev/null || break; sleep 2; done
pgrep -f CassandraDaemon && { kill $(cat $WORK/node/pid); sleep 5; }
pgrep -f CassandraDaemon || echo "no CassandraDaemon left"
pgrep -f MaxSizeProbe || echo "no probe left"
cp $WORK/node/logs/system.log $WORK/logs/p-m3-node-system.log 2>/dev/null
# B3e step 5
rm -rf $WORK/out $WORK/node
date -u +%FT%TZ; echo VALIDITY-DONE
