#!/usr/bin/env bash
# R12 monitors (identical in every arm; from B11's). Usage: monitor.sh <pid> <run dir> <tree>
# every 2 s: GC.heap_info + RssAnon + scope memory.current/events + debug.log* bytes + /mydata free (disk guard < 5 GiB);
# every 5 s: Thread.print summary; every 10 s target: RequestsSize/PausedConnections.
PID=$1; R=$2; T=$3; H=$(dirname "$0")
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup)
echo "cgroup $CG" > $R/mon-meta.txt
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    av=$(df -B1 --output=avail /mydata | tail -1 | tr -dc 0-9)
    if [ "$av" -lt 5368709120 ]; then echo "$ts avail=$av" > $R/DISKGUARD; kill -9 $PID; break; fi
    dl=$(stat -c %s $T/logs/debug.log* 2>/dev/null | awk '{s+=$1} END{print s+0}')
    hi=$(timeout 10 jcmd $PID GC.heap_info 2>/dev/null | tr '\n' '|')
    rss=$(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)
    mc=$(cat $CG/memory.current 2>/dev/null)
    echo "$ts rssanon_kb=$rss memcur=$mc debuglog=$dl avail=$av $hi" >> $R/heapinfo.txt
    sleep 2
  done ) &
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadcount.py)
    echo "$ts $l" >> $R/threads.txt
    sleep 5
  done ) &
( while kill -0 $PID 2>/dev/null; do
    ts=$(date +%s.%N | cut -c1-14)
    rs=$(timeout 20 $T/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -f Value --get 2>/dev/null | tail -1)
    pc=$(timeout 20 $T/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=PausedConnections -f Value --get 2>/dev/null | tail -1)
    echo "$ts requestssize=$rs paused=$pc" >> $R/ksrv.txt
    sleep 10
  done ) &
wait
