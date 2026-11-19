#!/usr/bin/env bash
# U7 monitors (identical in every arm, §2.6). Usage: monitor.sh <pid> <run dir> <stopfile>
# heap_info + RssAnon every 2 s; Thread.print NTR top frames every 5 s; one JMX poller JVM every 2 s; df every 10 s.
# Runs without a heap dump ($R/nodump exists, search runs >= 8 GiB): one GC.class_histogram (forces a full GC, §2.6)
# at the first heap_info sample with used >= 75 % of the heap.
PID=$1; R=$2; STOP=$3; H=$(dirname "$0")
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    ts=$(date +%s.%N | cut -c1-14)
    hi=$(timeout 10 jcmd $PID GC.heap_info 2>/dev/null | tr '\n' '|')
    rss=$(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)
    echo "$ts rssanon_kb=$rss $hi" >> $R/heapinfo.txt
    if [ -e $R/nodump ] && [ ! -e $R/class-histo.txt ]; then
      u=$(echo "$hi" | grep -o -E 'total [0-9]+K, used [0-9]+K' | head -1 | tr -dc '0-9 ' )
      set -- $u
      if [ -n "${2:-}" ] && [ $(( $2 * 100 )) -ge $(( $1 * 75 )) ]; then
        echo "class histogram at $ts (used $2 K of $1 K)" > $R/class-histo.txt
        timeout 600 jcmd $PID GC.class_histogram 2>&1 | head -45 >> $R/class-histo.txt
        echo "done $(date +%s.%N | cut -c1-14)" >> $R/class-histo.txt
      fi
    fi
    sleep 2
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    ts=$(date +%s.%N | cut -c1-14)
    l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadtop.py)
    echo "$ts $l" >> $R/threads.txt
    sleep 5
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    echo "$(date +%s) $(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)" >> $R/df.txt
    sleep 10
  done ) &
M=org.apache.cassandra.metrics
echo "epoch_ms,requestssize,paused,mem_t,mutstage_pending,ntr_active,ntr_pending,direct_used,heap_used" > $R/jmx.csv
java -cp $H Jmx 7199 poll 2000 100000 $STOP \
  $M:type=Client,name=RequestsSize Value \
  $M:type=Client,name=PausedConnections Value \
  $M:type=Table,keyspace=u7,scope=t,name=AllMemtablesHeapSize Value \
  $M:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks Value \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks Value \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks Value \
  java.nio:type=BufferPool,name=direct MemoryUsed \
  java.lang:type=Memory HeapMemoryUsage >> $R/jmx.csv 2>> $R/jmx.err &
wait
