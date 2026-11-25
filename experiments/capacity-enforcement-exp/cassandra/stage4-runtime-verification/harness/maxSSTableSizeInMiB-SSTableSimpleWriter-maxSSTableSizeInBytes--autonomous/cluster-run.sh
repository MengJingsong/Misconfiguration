#!/bin/bash
# Stage-4 cluster tier (B3e, with S4) for maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous, run 1.
# Runs on pc82 (x86_64). Logs every command and its output; stops at the first failed step; always stops the node.
set -euo pipefail
S4=/mydata/jingsong-cass-s4/o117
C=$S4/cluster
SRC=$C/cassandra-5.0.9
NODE=$C/node
GEN=$C/gen
LOG=$S4/logs
mkdir -p $LOG
exec > >(tee -a $LOG/cluster-run.log) 2>&1
set -x
date -u +%FT%TZ; hostname; uname -m
TABLES="t_m1 t_m4 t_m16 t_unset t_ctl"

stop_node() {
  set +e
  if [ -f $NODE/started.pid ]; then
    P=$(cat $NODE/started.pid)
    kill $P 2>/dev/null
    for i in $(seq 1 90); do kill -0 $P 2>/dev/null || break; sleep 1; done
    kill -0 $P 2>/dev/null && kill -9 $P
    rm -f $NODE/started.pid
  fi
  ps -eo pid,cmd | grep -E '[C]assandraDaemon|[G]enSorted' | grep -F "$C" | cut -c1-160
  echo "node stopped"
}
trap stop_node EXIT

# B3a (S4): copy built base; yaml
# S7 / D1: the tier restarts from its beginning: remove attempt 1's cluster folder and copy the base afresh
rm -rf $C; mkdir -p $C; cp -a /mydata/s4/cassandra-base $SRC
REPO_SRC=/proj/misconfiguration-PG0/git-repos/Misconfiguration/systems/cassandra/source
diff -rq $SRC/src/java $REPO_SRC/src/java && echo SRC_JAVA_SAME
diff -rq $SRC/test/unit $REPO_SRC/test/unit && echo TEST_UNIT_SAME
mkdir -p $NODE/{data,commitlog,saved_caches,hints,cdc} $GEN/out
Y=$SRC/conf/cassandra.yaml
sed -i 's/^listen_address: localhost$/listen_address: 127.0.0.1/; s/^rpc_address: localhost$/rpc_address: 127.0.0.1/' $Y
# S7 / D1: CQLSSTableWriter (client mode) always writes the 5.0 BIG version 'oa'; a node in the default
# CASSANDRA_4 mode lists 'oa' as incompatible and nodetool import silently finds nothing. Fresh node in NONE mode.
sed -i 's/^storage_compatibility_mode: CASSANDRA_4$/storage_compatibility_mode: NONE/' $Y
cat >> $Y <<EOF

# --- stage-4 o117 (S4) ---
data_file_directories:
    - $NODE/data
commitlog_directory: $NODE/commitlog
saved_caches_directory: $NODE/saved_caches
hints_directory: $NODE/hints
cdc_raw_directory: $NODE/cdc
EOF
grep -nE '^(storage_compatibility_mode|listen_address|rpc_address|data_file_directories|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory|partitioner)|^    - /|seeds:' $Y
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { echo "STEP_FAIL port $p busy"; exit 1; }; done

# generator
CP="$SRC/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$SRC/build/lib/jars/*"
cp $S4/harness/GenSorted.java $GEN/
javac -cp "$CP" -d $GEN $GEN/GenSorted.java
JOPTS=$(grep -v '^#' $SRC/conf/jvm11-clients.options | xargs)

# B3e step 2: start node
cd $SRC
ulimit -n 100000
export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
bin/cassandra -p $NODE/cassandra.pid > $NODE/stdout.log 2>&1
for i in $(seq 1 60); do [ -s $NODE/cassandra.pid ] && break; sleep 1; done
cp $NODE/cassandra.pid $NODE/started.pid
UP=0
for i in $(seq 1 120); do
  kill -0 $(cat $NODE/started.pid) 2>/dev/null || { echo "STEP_FAIL daemon died"; tail -30 $SRC/logs/system.log; exit 1; }
  if bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(bin/nodetool statusbinary 2>/dev/null)" = running ]; then UP=1; break; fi
  sleep 3
done
[ $UP = 1 ] || { echo "STEP_FAIL node not up"; exit 1; }
bin/nodetool status
ps -o pid,args -p $(cat $NODE/started.pid) | tr ' ' '\n' | grep -E 'Xmx|Xms|Xmn' | head

# B3e step 3: schema
bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE s4ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};"
for T in $TABLES; do
  bin/cqlsh 127.0.0.1 -e "CREATE TABLE s4ks.$T (k int PRIMARY KEY, v blob) WITH compression = {'enabled':'false'};"
  bin/nodetool disableautocompaction s4ks $T
done
bin/cqlsh 127.0.0.1 -e "DESCRIBE TABLE s4ks.t_m1" > $LOG/cluster-schema.txt

# B3e step 4: generate
gen() { local T=$1 M=$2 MODE=$3; local t0=$(date +%s)
  java $JOPTS -Xmx1G -cp "$GEN:$CP:$SRC/conf" GenSorted $GEN/out/$T/s4ks/$T $T $M $MODE 60000 > $LOG/gen-$T.log 2>&1 || { tail -40 $LOG/gen-$T.log; echo "STEP_FAIL gen $T"; exit 1; }
  echo "gen $T M=$M $MODE: $(( $(date +%s) - t0 )) s"; }
gen t_m1 1 sorted
gen t_m4 4 sorted
gen t_m16 16 sorted
gen t_unset unset sorted
gen t_ctl 4 unsorted

# B3e step 5: generator-side sizes
for d in $GEN/out/*/s4ks/*; do echo $d; stat -c '%s %n' $d/*-Data.db; du -sb $d; done | tee $LOG/sizes-gen.txt
for d in $GEN/out/*/s4ks/*; do stat -c '%s %n' $d/*; done > $LOG/sizes-gen-all.txt

# B3e step 6: import
for T in $TABLES; do bin/nodetool import --copy-data s4ks $T $GEN/out/$T/s4ks/$T; done
# S7 / D1: stop at once if an import brought nothing in
for T in $TABLES; do N=$(bin/nodetool tablestats s4ks.$T | awk -F: '/\tSSTable count/{gsub(/ /,"",$2); print $2; exit}'); echo "$T imported SSTables: $N"; [ "${N:-0}" -gt 0 ] || { echo "STEP_FAIL import $T brought no SSTables"; exit 1; }; done

# B3e step 7: node-side sizes and row counts
for T in $TABLES; do
  echo "== $T"; bin/nodetool tablestats s4ks.$T | grep -E 'SSTable count|Space used \(live\)'
  stat -c '%s %n' $NODE/data/s4ks/$T-*/*-Data.db
done | tee $LOG/sizes-node.txt
for T in $TABLES; do
  echo "== $T"; bin/cqlsh 127.0.0.1 --request-timeout=120 -e "CONSISTENCY ONE; SELECT count(*) FROM s4ks.$T;"
done | tee $LOG/rowcounts.txt
bin/nodetool compactionstats | tee $LOG/compactionstats.txt
cp $SRC/logs/system.log $LOG/node-system.log

# B3e step 8: stop
stop_node
trap - EXIT
sleep 2
ps -eo cmd | grep -E '[C]assandraDaemon|[G]enSorted' | cut -c1-150 || echo "no CassandraDaemon/GenSorted left"
date -u +%FT%TZ
echo CLUSTER_DONE
