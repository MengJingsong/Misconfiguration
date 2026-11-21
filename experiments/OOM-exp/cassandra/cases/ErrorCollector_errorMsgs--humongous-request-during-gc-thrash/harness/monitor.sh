#!/usr/bin/env bash
# R15 monitors (copy of U6 monitor.sh; unchanged). U6 monitors (identical in every arm). Usage: monitor.sh <pid> <run dir> <stopfile>
# heap_info + RssAnon every 3 s; Thread.print summary every 10 s; one JMX poller JVM every 5 s; df + client CPU every 10 s.
PID=$1; R=$2; STOP=$3; H=$(dirname "$0")
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    ts=$(date +%s.%N | cut -c1-14)
    hi=$(timeout 10 jcmd $PID GC.heap_info 2>/dev/null | tr '\n' '|')
    rss=$(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)
    echo "$ts rssanon_kb=$rss $hi" >> $R/heapinfo.txt
    sleep 3
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    ts=$(date +%s.%N | cut -c1-14)
    if [ -n "${R15_DIAG:-}" ]; then   # R15 amendment 2026-11-20 (diagnostic runs only): keep every full thread dump
      timeout 15 jcmd $PID Thread.print > $R/.td.tmp 2>/dev/null
      { echo "=== $ts"; cat $R/.td.tmp; } >> $R/threads-full.txt
      l=$(python3 -I $H/threadcount.py < $R/.td.tmp)
    else
      l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadcount.py)
    fi
    echo "$ts $l" >> $R/threads.txt
    sleep 10
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    echo "$(date +%s) $(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9) $(cut -d' ' -f1-3 /proc/loadavg)" >> $R/df.txt
    ps -o pid=,pcpu=,rss= -C python3 | tr '\n' ';' | sed "s/^/$(date +%s) /" >> $R/clientcpu.txt; echo >> $R/clientcpu.txt
    sleep 10
  done ) &
M=org.apache.cassandra.metrics
echo "epoch_ms,requestssize,paused,ntr_active,ntr_pending,direct_used,heap_used" > $R/jmx.csv
java -cp $H Jmx 7199 poll 5000 100000 $STOP \
  $M:type=Client,name=RequestsSize Value \
  $M:type=Client,name=PausedConnections Value \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks Value \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks Value \
  java.nio:type=BufferPool,name=direct MemoryUsed \
  java.lang:type=Memory HeapMemoryUsage >> $R/jmx.csv 2>> $R/jmx.err &
wait
