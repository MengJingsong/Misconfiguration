#!/bin/bash
# Cluster tier (B3e as amended by B3i). Steps: live | oom | node | all
set -u
. /mydata/jingsong-cass-s4/o115/harness/common.sh
mkdir -p $OUTD
STEP=${1:-all}
exec > >(tee -a $OUTD/cluster-driver-$STEP.log) 2>&1
echo "=== cluster-run.sh $STEP start $(date -Is) epoch_ms=$(date +%s%3N) host=$(hostname) arch=$(uname -m)"
df -h $S4 | tail -1; free -g | head -2
[ -d $S4/harness/classes ] || { echo "harness not compiled"; exit 1; }

live() {
  no_strays || return 1
  for R in C16 C32 C64 C128 CX; do
    case $R in C16) M=explicit:16;; C32) M=explicit:32;; C64) M=explicit:64;; C128) M=default;; CX) M=explicit:2047;; esac
    OUT=$OUTD/$R/probe/t; rm -rf $OUTD/$R; mkdir -p $OUT
    echo "--- $R start $(date -Is) mode=$M"
    set -x
    probe_cluster 2g $OUTD/gc-$R.log $OUT $M 18000 60000 false 250 2>&1 | tee $OUTD/$R.log
    rc=${PIPESTATUS[0]}
    set +x
    echo "EXIT $rc" | tee -a $OUTD/$R.log
    stat -c '%s %n' $OUT/*-Data.db >> $OUTD/$R.log 2>&1
    echo "DATA_DB_COUNT $(ls $OUT/*-Data.db 2>/dev/null | wc -l)" | tee -a $OUTD/$R.log
    du -sb $OUT | tee -a $OUTD/$R.log
    [ $R = C128 ] || rm -rf $OUTD/$R
    echo "--- $R end $(date -Is) rc=$rc"
    [ $rc = 0 ] || { echo "$R failed"; return 1; }
  done
  no_strays
}

oom() {
  no_strays || return 1
  for spec in C128:256m C128:384m C128:512m C128:768m C16:256m CX:768m; do
    R=${spec%%:*}; X=${spec##*:}
    case $R in C16) M=explicit:16;; C128) M=default;; CX) M=explicit:2047;; esac
    N=oom-$R-$X; OUT=$OUTD/$N/probe/t; rm -rf $OUTD/$N; mkdir -p $OUT
    echo "--- $N start $(date -Is)"
    set -x
    probe_cluster $X $OUTD/gc-$N.log $OUT $M 18000 60000 false 0 2>&1 | tee $OUTD/$N.log
    rc=${PIPESTATUS[0]}
    set +x
    echo "EXIT $rc" | tee -a $OUTD/$N.log
    echo "OOM_LINES $(grep -c OutOfMemoryError $OUTD/$N.log)" | tee -a $OUTD/$N.log
    echo "DATA_DB_COUNT $(ls $OUT/*-Data.db 2>/dev/null | wc -l)" | tee -a $OUTD/$N.log
    rm -rf $OUTD/$N
    echo "--- $N end $(date -Is) rc=$rc"
  done
  no_strays
}

node() {
  [ -d $OUTD/C128/probe/t ] || { echo "no C128 output"; return 1; }
  if ss -ltn | grep -E ':(7000|7199|9042)\b'; then echo "ports in use"; return 1; fi
  no_strays || return 1
  cd $SRC
  ulimit -n 100000
  set -x
  MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M bin/cassandra -p $S4/node.pid > $OUTD/node-start.log 2>&1
  set +x
  ok=0
  for i in $(seq 1 36); do
    sleep 5
    if ! ps -eo cmd | grep -q '[C]assandraDaemon'; then echo "node died during start"; tail -50 $SRC/logs/system.log; return 1; fi
    if bin/nodetool status 2>/dev/null | grep -q '^UN' && bin/nodetool statusbinary 2>/dev/null | grep -q running; then ok=1; break; fi
  done
  [ $ok = 1 ] || { echo "node not UN within 3 min"; return 1; }
  echo "node UN + binary running at $(date -Is) pid=$(cat $S4/node.pid)"
  set -x
  bin/cqlsh -e "CREATE KEYSPACE probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE probe.t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled':'false'};"
  bin/sstableloader -d 127.0.0.1 $OUTD/C128/probe/t > $OUTD/load-raw.log 2>&1
  echo "SSTABLELOADER_EXIT $?" | tee $OUTD/load.log
  grep -vE '^progress:' $OUTD/load-raw.log | tail -40 >> $OUTD/load.log
  tail -c 2000 $OUTD/load-raw.log | tr '\r' '\n' | tail -3 >> $OUTD/load.log
  bin/nodetool flush probe t
  bin/nodetool tablestats probe.t | tee -a $OUTD/load.log
  du -sb $SRC/data/data/probe | tee -a $OUTD/load.log
  bin/cqlsh --request-timeout=600 -e "SELECT count(*) FROM probe.t" 2>&1 | tee -a $OUTD/load.log
  bin/nodetool compactionstats | tee -a $OUTD/load.log
  set +x
}

stop_node() {
  if [ -f $S4/node.pid ]; then
    P=$(cat $S4/node.pid); echo "stopping node pid $P"
    kill $P 2>/dev/null
    for i in $(seq 1 12); do ps -p $P >/dev/null 2>&1 || break; sleep 5; done
    ps -p $P >/dev/null 2>&1 && { echo "kill -9 $P"; kill -9 $P; sleep 2; }
    rm -f $S4/node.pid
  fi
  cp $SRC/logs/system.log $OUTD/node-system.log 2>/dev/null
  no_strays
}

case $STEP in
  live) live ;;
  oom) oom ;;
  node) node; rc=$?; stop_node; [ $rc = 0 ] || echo "node step failed rc=$rc" ;;
  all) live && oom && { node; rc=$?; stop_node; } ;;
esac
echo "=== cluster-run.sh $STEP end $(date -Is)"
