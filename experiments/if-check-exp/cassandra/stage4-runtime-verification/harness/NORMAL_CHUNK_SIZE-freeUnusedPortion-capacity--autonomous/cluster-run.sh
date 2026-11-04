#!/bin/bash
# Cluster tier (case file B3e, amended 2026-10-22) of NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous, one NCS value.
# usage: bash cluster-run.sh <label> <NCS MiB>      e.g. bash cluster-run.sh V16 16
# Run from a frozen copy of the harness (~/stage4-harness-run/ncs/), never edited while running.
# Environment deviations (shared host pc07, another stage-4 agent on 127.0.0.5 / JMX 7205): nodes on 127.0.0.4 (seed, JMX 7204)
# and 127.0.0.6 (JMX 7206) instead of 127.0.0.1 / .2 (7199 / 7299); paths ~/stage4-ncs, ~/stage4-logs/ncs instead of /tmp/s3bp;
# cluster_name 'ncs-stage4'; nodes matched by 'cassandra-ncs' in the java command line, never by a bare CassandraDaemon pattern.
# Amendments applied (case file, 2026-10-22): K1 Byteman ncs.btm (made/refuse/guard/ovftrim) and the one-connection JMX sampler;
# K3 write n=1,500,000 and read n=1,000,000 (disk); K4 the 8 MiB value. Observables otherwise as B3d.
set -u
R=$1; NCS=$2
C=$HOME/cassandra-ncs; H=$HOME/stage4-harness-run/ncs; W=$HOME/stage4-ncs; LOG=$HOME/stage4-logs/ncs/cluster/$R
A1=127.0.0.4; A2=127.0.0.6; J1=7204; J2=7206
rm -rf $LOG; mkdir -p $LOG
exec > >(tee -a $LOG/run.log) 2>&1
NT() { $C/bin/nodetool -h 127.0.0.1 -p $1 "${@:2}"; }
mypids() { ps -eo pid,args | grep '[j]ava' | grep 'cassandra-ncs' | grep CassandraDaemon | awk '{print $1}'; }
SAMPLERS=""
cleanup() {
  touch $W/stop
  [ -n "${SAMPLERS:-}" ] && wait $SAMPLERS 2>/dev/null   # never a bare wait (tee process substitution)
  for p in $(ps -eo pid,args | grep '[j]ava' | grep cassandra-ncs | grep -i stress | awk '{print $1}'); do kill $p; done
  if [ -n "$(mypids)" ]; then
    echo "== stopping nodes"; NT $J2 stopdaemon >/dev/null 2>&1; NT $J1 stopdaemon >/dev/null 2>&1
    for i in $(seq 1 40); do [ -z "$(mypids)" ] && break; sleep 1; done
    for p in $(mypids); do kill $p; done; sleep 5; for p in $(mypids); do kill -9 $p; done
  fi
  echo "leftover cassandra-ncs java: $(ps -eo pid,args | grep '[j]ava' | grep -c cassandra-ncs)"
  rm -rf $W/n4/{data,commitlog,saved_caches,hints,cdc_raw} $W/n6/{data,commitlog,saved_caches,hints,cdc_raw}
  du -sh $W 2>/dev/null; df -h $HOME | tail -1
  echo "== $(date -Is) $R cleanup done"
}
trap cleanup EXIT
trap "exit 1" INT TERM
fail() { echo "FAIL: $*"; exit 1; }
echo "== $(date -Is) $R networking_cache_size=${NCS}MiB"
[ -n "$(mypids)" ] && fail "a cassandra-ncs node is already running"
ss -ltn | grep -E "($A1|$A2):(7000|9042)\b|127.0.0.1:($J1|$J2)\b" && fail "port in use"
sha256sum $H/* | tee $LOG/harness-sha256.txt
df -h $HOME | tail -1
FREE=$(df --output=avail -BG $HOME | tail -1 | tr -dc 0-9); [ "$FREE" -lt 15 ] && fail "less than 15 GB free"
ulimit -n 100000
BM=$C/build/lib/jars/byteman-4.0.20.jar
setup_node() {  # $1 = n4|n6, $2 = address, $3 = jmx port
  local N=$W/$1; rm -rf $N; mkdir -p $N/{data,commitlog,hints,saved_caches,cdc_raw}; cp -r $C/conf $N/conf
  local Y=$N/conf/cassandra.yaml
  sed -i -e "s|^cluster_name:.*|cluster_name: 'ncs-stage4'|" \
    -e "s|^listen_address:.*|listen_address: $2|" \
    -e "s|^rpc_address:.*|rpc_address: $2|" \
    -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"$A1:7000\"|" \
    -e "s|^# data_file_directories:.*|data_file_directories: [$N/data]|" \
    -e "s|^# commitlog_directory:.*|commitlog_directory: $N/commitlog|" \
    -e "s|^# hints_directory:.*|hints_directory: $N/hints|" \
    -e "s|^# saved_caches_directory:.*|saved_caches_directory: $N/saved_caches|" \
    -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $N/cdc_raw|" \
    -e "s|^# networking_cache_size:.*|networking_cache_size: ${NCS}MiB|" $Y
  sed -i "s|^JMX_PORT=\"7199\"|JMX_PORT=\"$3\"|" $N/conf/cassandra-env.sh
  diff <(git -C $C show HEAD:conf/cassandra.yaml) $Y > $LOG/yaml-$1.diff
  echo "-- $1 yaml diff"; cat $LOG/yaml-$1.diff; grep -n '^JMX_PORT' $N/conf/cassandra-env.sh
}
start_node() {  # $1 = n4|n6, $2 = address, $3 = jmx port
  local N=$W/$1
  date +%s%3N > $LOG/t-start-$1
  CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$LOG/$1-logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M \
  JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=2g -javaagent:$BM=script:$H/ncs.btm -Dstage4.byteman.out=$LOG/bm-$1.txt" \
    $C/bin/cassandra -p $N/cassandra.pid > $LOG/out-$1.log 2>&1
  local i
  for i in $(seq 1 100); do
    sleep 3
    kill -0 $(cat $N/cassandra.pid 2>/dev/null) 2>/dev/null || { sleep 2; kill -0 $(cat $N/cassandra.pid 2>/dev/null) 2>/dev/null || fail "$1 died during start"; }
    grep -q 'Starting listening for CQL clients' $LOG/$1-logs/system.log 2>/dev/null && NT $3 statusbinary 2>/dev/null | grep -q running && break
  done
  NT $3 statusbinary | grep -q running || fail "$1 not up"
  echo "$1 up, pid $(cat $N/cassandra.pid), $(( ($(date +%s%3N) - $(cat $LOG/t-start-$1)) / 1000 )) s"
  grep 'Global buffer pool limit is' $LOG/$1-logs/system.log || fail "$1: no buffer pool limit line"
  echo "$1 out.log byteman/rule errors: $(grep -ciE 'byteman|ERROR : Rule|Rule.execute' $LOG/out-$1.log)"
}
setup_node n4 $A1 $J1
setup_node n6 $A2 $J2
start_node n4 $A1 $J1
start_node n6 $A2 $J2
for i in $(seq 1 40); do [ "$(NT $J1 status 2>/dev/null | grep -cE "^UN  ($A1|$A2) ")" = 2 ] && break; sleep 3; done
NT $J1 status | tee $LOG/status.txt
[ "$(grep -cE "^UN  ($A1|$A2) " $LOG/status.txt)" = 2 ] || fail "ring not 2 UN"
P4=$(cat $W/n4/cassandra.pid); P6=$(cat $W/n6/cassandra.pid)
# sampler: compiled once into $H/classes by the run driver
rm -f $W/stop
java -cp $H/classes PoolSampler $J1 $LOG/samples-n4.csv $W/stop 5000 & SAMPLERS="$!"
java -cp $H/classes PoolSampler $J2 $LOG/samples-n6.csv $W/stop 5000 & SAMPLERS="$SAMPLERS $!"
( while [ ! -f $W/stop ]; do echo "$(date +%s%3N) n4 $(ps -o rss= -p $P4) n6 $(ps -o rss= -p $P6)"; sleep 5; done ) > $LOG/rss.txt &
SAMPLERS="$SAMPLERS $!"
echo "== idle baseline 30 s"; date +%s%3N > $LOG/t-baseline; sleep 30
ST=$C/tools/bin/cassandra-stress
date +%s%3N > $LOG/t-start-write
$ST write n=1500000 cl=ALL -schema "replication(factor=2)" -col 'size=FIXED(512)' 'n=FIXED(5)' \
  -mode native cql3 protocolVersion=5 -rate threads=256 -node $A1,$A2 -port jmx=$J1 \
  -log file=$LOG/stress-write.log > $LOG/stress-write-console.log 2>&1
echo "write rc=$?"; date +%s%3N > $LOG/t-end-write
grep -E 'Op rate|Total partitions|Total errors|Total operation time' $LOG/stress-write-console.log
date +%s%3N > $LOG/t-start-read
$ST read n=1000000 cl=ALL -col 'size=FIXED(512)' 'n=FIXED(5)' -mode native cql3 protocolVersion=5 -rate threads=256 \
  -node $A1,$A2 -port jmx=$J1 -log file=$LOG/stress-read.log > $LOG/stress-read-console.log 2>&1
echo "read rc=$?"; date +%s%3N > $LOG/t-end-read
grep -E 'Op rate|Total partitions|Total errors|Total operation time' $LOG/stress-read-console.log
echo "== tail 60 s"; sleep 60
date +%s%3N > $LOG/t-end-tail
touch $W/stop; wait $SAMPLERS 2>/dev/null; SAMPLERS=""
for n in n4 n6; do
  echo "-- $n: 'Maximum memory usage reached' lines: $(grep -c 'Maximum memory usage reached' $LOG/$n-logs/system.log)"
  grep 'Maximum memory usage reached' $LOG/$n-logs/system.log | head -2
  echo "-- $n: ^ERROR lines: $(grep -c '^ERROR' $LOG/$n-logs/system.log); ^WARN lines: $(grep -c '^WARN' $LOG/$n-logs/system.log)"
  echo "-- $n: made lines $(grep -c '^made' $LOG/bm-$n.txt); last dump: $(grep '^dump' $LOG/bm-$n.txt | tail -1)"
  echo "-- $n: samples $(grep -vc ERR $LOG/samples-$n.csv), ERR $(grep -c ERR $LOG/samples-$n.csv)"
done
NT $J1 tablestats keyspace1.standard1 2>/dev/null | grep -E 'SSTable count|Space used \(live\)|Number of partitions'
du -sh $W/n4/data $W/n6/data
echo "== $(date -Is) $R done"
