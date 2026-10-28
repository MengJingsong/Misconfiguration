#!/usr/bin/env bash
# usage: node.sh start <A|B> [extra JVM options] | stop <A|B> | status     (helper for prep-data.sh and cluster-run.sh)
C=${CASSANDRA_HOME:-$HOME/c4-mrb}; R=${R:-$HOME/stage4-mrb}
daemons() { ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | wc -l; }
port() { case $1 in A) echo 7102;; B) echo 7103;; esac; }
addr() { case $1 in A) echo 127.0.0.2;; B) echo 127.0.0.3;; esac; }
case $1 in
  start)
    n=$2; shift 2; ulimit -n 100000; cd "$C"
    # -f (foreground, in the background of this shell): without it the daemon closes System.out after start-up and Byteman's traceln output is lost
    CASSANDRA_CONF=$R/$n/conf CASSANDRA_LOG_DIR=$R/$n/logs MAX_HEAP_SIZE=${HEAP:-2G} JVM_EXTRA_OPTS="$*" nohup bin/cassandra -f > $R/$n/stdout.txt 2>&1 &
    echo $! > $R/$n/cassandra.pid   # the script exec's java, so this is the daemon's pid
    for i in $(seq 1 100); do
      s=$(bin/nodetool -p $(port $n) statusbinary 2>/dev/null | tr -d '\n'); [ "$s" = running ] && { echo "node $n up"; exit 0; }
      pgrep -F $R/$n/cassandra.pid >/dev/null 2>&1 || { echo "node $n died at start"; tail -20 $R/$n/stdout.txt; exit 1; }
      sleep 3
    done
    echo "node $n did not come up"; exit 1 ;;
  stop)
    n=$2; cd "$C"; [ -f $R/$n/cassandra.pid ] || exit 0
    bin/nodetool -p $(port $n) stopdaemon >/dev/null 2>&1
    for i in $(seq 1 60); do pgrep -F $R/$n/cassandra.pid >/dev/null 2>&1 || break; sleep 2; done
    pgrep -F $R/$n/cassandra.pid >/dev/null 2>&1 && { echo "node $n did not stop, kill -9"; kill -9 $(cat $R/$n/cassandra.pid); sleep 2; }
    exit 0 ;;
  status) daemons ;;
esac
