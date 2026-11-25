#!/usr/bin/env bash
# o116 client-process tier: B3e as written (S4-A1 paths and node-start safety). Every command echoed (set -x).
set -x
W=/mydata/jingsong-cass-s4/o116; SRC=$W/src; RUN=$W/run
CP="$SRC/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$SRC/build/lib/jars/*"
JOPTS="$(grep -v '^#' $SRC/conf/jvm11-clients.options | grep -v '^$' | xargs)"
JOPTS="$JOPTS -Dlogback.configurationFile=$SRC/conf/logback-tools.xml"   # S4-A4(d): logging only
date -u +%FT%TZ; uptime; free -g
cd $RUN/p
bulk() {  # $1=name $2=mib $3=Xmx
  date -u +%FT%TZ
  rm -rf $RUN/p/out-$1; mkdir -p $RUN/p/out-$1/probe_ks/t
  ( java $JOPTS -Xmx$3 -Xlog:gc:file=$RUN/p/gc-$1.log -cp "$CP:." BulkProbe $2 524288 $RUN/p/out-$1/probe_ks/t \
      > $RUN/p/$1.out 2>&1; echo "exit=$?" >> $RUN/p/$1.out ) &
  P=$!; t0=$(date +%s); oomt=0
  while kill -0 $P 2>/dev/null; do
    ps -o rss= --ppid $P >> $RUN/p/rss-$1.txt; sleep 1
    # S4-A4(c) watchdog: >1800 s, or still alive 60 s after OutOfMemoryError appeared (non-daemon DiskWriter)
    now=$(date +%s)
    if [ $oomt = 0 ] && grep -q OutOfMemoryError $RUN/p/$1.out 2>/dev/null; then oomt=$now; fi
    if [ $((now - t0)) -gt 1800 ] || { [ $oomt != 0 ] && [ $((now - oomt)) -gt 60 ]; }; then
      J=$(ps -o pid= --ppid $P); echo "WATCHDOG-KILL pid=$J elapsed=$((now - t0)) oomSeenAt=$oomt" | tee -a $RUN/p/$1.out
      kill $J; sleep 5; kill -9 $J 2>/dev/null
    fi
  done
  ls -l $RUN/p/out-$1/probe_ks/t/*-Data.db > $RUN/p/data-$1.txt 2>/dev/null; du -sb $RUN/p/out-$1 >> $RUN/p/data-$1.txt
  grep -oE '[0-9]+M->[0-9]+M' $RUN/p/gc-$1.log | sed 's/.*->//; s/M//' | sort -n | tail -1 > $RUN/p/peak-$1.txt
  tail -2 $RUN/p/$1.out; grep -m1 OutOfMemoryError $RUN/p/$1.out; echo "files=$(grep -c Data.db $RUN/p/data-$1.txt) peak=$(cat $RUN/p/peak-$1.txt)"; tail -1 $RUN/p/data-$1.txt
}
bulk m16  16  2g; rm -rf $RUN/p/out-m16
bulk m64  64  2g; rm -rf $RUN/p/out-m64
bulk mdef -1  2g; rm -rf $RUN/p/out-mdef
bulk m256 256 2g; rm -rf $RUN/p/out-m256
bulk x16  16  256m; rm -rf $RUN/p/out-x16
bulk x256 256 256m; rm -rf $RUN/p/out-x256
cp $RUN/p/data-m16.txt $RUN/p/data-m16-first.txt; cp $RUN/p/peak-m16.txt $RUN/p/peak-m16-first.txt; cp $RUN/p/m16.out $RUN/p/m16-first.out; cp $RUN/p/gc-m16.log $RUN/p/gc-m16-first.log
rm -f $RUN/p/rss-m16.txt.keep; mv $RUN/p/rss-m16.txt $RUN/p/rss-m16-first.txt
bulk m16  16  2g                                   # rerun, output kept for the load step
ps -eo pid,cmd | grep '[B]ulkProbe' || echo "no BulkProbe left"

# load step (single node); B3a node config
rm -rf $RUN/conf $RUN/node; mkdir -p $RUN/node/logs; cp -a $SRC/conf $RUN/conf
python3 - $RUN/conf/cassandra.yaml $RUN/node <<'PY'
import sys,re
y,n=sys.argv[1],sys.argv[2]
s=open(y).read()
s,c1=re.subn(r'(?m)^# data_file_directories:\n#     - /var/lib/cassandra/data', 'data_file_directories:\n    - %s/data'%n, s)
s,c2=re.subn(r'(?m)^# commitlog_directory:.*$', 'commitlog_directory: %s/commitlog'%n, s)
s,c3=re.subn(r'(?m)^# hints_directory:.*$', 'hints_directory: %s/hints'%n, s)
s,c4=re.subn(r'(?m)^# saved_caches_directory:.*$', 'saved_caches_directory: %s/saved_caches'%n, s)
s,c5=re.subn(r'(?m)^# cdc_raw_directory:.*$', 'cdc_raw_directory: %s/cdc_raw'%n, s)
s,c6=re.subn(r'(?m)^listen_address:.*$', 'listen_address: 127.0.0.1', s)
s,c7=re.subn(r'(?m)^rpc_address:.*$', 'rpc_address: 127.0.0.1', s)
s,c8=re.subn(r'(?m)^storage_compatibility_mode:.*$', 'storage_compatibility_mode: NONE', s)   # S4-A4(e)
print("subs", c1,c2,c3,c4,c5,c6,c7,c8)
open(y,'w').write(s)
PY
grep -nE '^(data_file_directories|    - /mydata|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|partitioner|storage_compatibility_mode)' $RUN/conf/cassandra.yaml
ss -ltn | grep -E ':(7000|9042|7199) ' && { echo "PORTS BUSY"; exit 1; }
ulimit -n 100000
cd $SRC && CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/node/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M bin/cassandra -p $RUN/node.pid > $RUN/node/logs/start.out 2>&1
sleep 3; cat $RUN/node.pid; echo
ok=0
for i in $(seq 1 90); do
  ps -eo cmd | grep -q '[C]assandraDaemon' || { echo "daemon died"; break; }
  if CASSANDRA_CONF=$RUN/conf bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$(CASSANDRA_CONF=$RUN/conf bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
echo "node_up=$ok"
if [ $ok = 1 ]; then
  bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE probe_ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
    CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'};"
  CASSANDRA_CONF=$RUN/conf bin/sstableloader -d 127.0.0.1 --no-progress $RUN/p/out-m16/probe_ks/t > $RUN/p/loader.log 2>&1; echo "loader_exit=$?"; tail -8 $RUN/p/loader.log
  grep -qiE 'Total files transferred *: *[1-9]|Total bytes transferred *: *[1-9]|Summary statistics' $RUN/p/loader.log || echo "LOADER-STREAMED-NOTHING (S4-A4(e))"
  CASSANDRA_CONF=$RUN/conf bin/nodetool flush probe_ks t; CASSANDRA_CONF=$RUN/conf bin/nodetool tablestats probe_ks.t > $RUN/p/node-tablestats.txt; grep -E 'SSTable count|Space used \(live\)|Number of partitions' $RUN/p/node-tablestats.txt
  bin/cqlsh 127.0.0.1 -e "SELECT count(*) FROM probe_ks.t WHERE k = 0; SELECT count(*) FROM probe_ks.t WHERE k = 32767;" > $RUN/p/node-cqlsh.txt 2>&1; cat $RUN/p/node-cqlsh.txt
fi
# B4 stop
CASSANDRA_CONF=$RUN/conf bin/nodetool stopdaemon || kill $(cat $RUN/node.pid)
for i in $(seq 1 30); do ps -eo cmd | grep -q '[C]assandraDaemon' || break; sleep 2; done
ps -eo cmd | grep -q '[C]assandraDaemon' && { kill $(cat $RUN/node.pid); sleep 5; kill -9 $(cat $RUN/node.pid) 2>/dev/null; }
ps -eo pid,cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon left"
ps -eo pid,cmd | grep '[B]ulkProbe' || echo "no BulkProbe left"
cp $RUN/node/logs/system.log $RUN/p/node-system.log 2>/dev/null
date -u +%FT%TZ; echo CLUSTER-DONE
