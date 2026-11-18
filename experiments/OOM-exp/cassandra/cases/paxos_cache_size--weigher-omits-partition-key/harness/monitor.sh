#!/usr/bin/env bash
# B12 monitors (identical in every arm). Usage: monitor.sh <pid> <run dir> <tree>
# GC.heap_info + RssAnon + scope memory.current every 2 s; every ~10 s (sequential nodetool sjk calls, then 10 s sleep):
# CASRead / Read client-request latency Count and b12.t CasPrepareLatency / CasProposeLatency Count.
PID=$1; R=$2; T=$3
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
echo "cgroup $CG" > $R/mon-meta.txt
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    hi=$(timeout 10 jcmd $PID GC.heap_info 2>/dev/null | tr '\n' '|')
    rss=$(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)
    mc=$(cat $CG/memory.current 2>/dev/null)
    echo "$ts rssanon_kb=$rss memcur=$mc $hi" >> $R/heapinfo.txt
    sleep 2
  done ) &
mx(){ timeout 30 $T/bin/nodetool sjk mx -b "$1" -f Count --get 2>/dev/null | tail -1; }
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    a=$(mx org.apache.cassandra.metrics:type=ClientRequest,scope=CASRead,name=Latency)
    b=$(mx org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Latency)
    c=$(mx org.apache.cassandra.metrics:type=Table,keyspace=b12,scope=t,name=CasPrepareLatency)
    d=$(mx org.apache.cassandra.metrics:type=Table,keyspace=b12,scope=t,name=CasProposeLatency)
    echo "$ts casread=$a read=$b casprepare=$c caspropose=$d" >> $R/metrics.txt
    sleep 10
  done ) &
wait
