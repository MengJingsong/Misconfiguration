#!/usr/bin/env bash
# R13 3-b confirm monitors (2026-11-23; from stage 2's monitor.sh: r13 memtable / MutationStage columns replaced by
# client-connection metrics: ConnectedNativeClients, ProtocolException, AuthSuccess, RequestDiscarded). Usage: monitor.sh <pid> <run dir> <stopfile>
# heap_info + RssAnon every 3 s; Thread.print summary every 5 s; one JMX poller JVM every 5 s; df + client cpu every 10 s.
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
    l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadcount.py)
    echo "$ts $l" >> $R/threads.txt
    sleep 5
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    echo "$(date +%s) $(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)" >> $R/df.txt
    ps -o pid=,pcpu=,rss= -C python3 | tr '\n' ';' | sed "s/^/$(date +%s) /" >> $R/clientcpu.txt; echo >> $R/clientcpu.txt
    sleep 10
  done ) &
M=org.apache.cassandra.metrics
echo "epoch_ms,requestssize,paused,connected,protocol_exc,auth_success,ntr_active,ntr_pending,direct_used,heap_used,write_count,write_timeouts,req_discarded,netpool_size,netpool_overflow" > $R/jmx.csv
java -cp $H Jmx 7199 poll 5000 100000 $STOP \
  $M:type=Client,name=RequestsSize Value \
  $M:type=Client,name=PausedConnections Value \
  $M:type=Client,name=ConnectedNativeClients Value \
  $M:type=Client,name=ProtocolException Count \
  $M:type=Client,name=AuthSuccess Count \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks Value \
  $M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks Value \
  java.nio:type=BufferPool,name=direct MemoryUsed \
  java.lang:type=Memory HeapMemoryUsage \
  $M:type=ClientRequest,scope=Write,name=Latency Count \
  $M:type=ClientRequest,scope=Write,name=Timeouts Count \
  $M:type=Client,name=RequestDiscarded Count \
  $M:type=BufferPool,scope=networking,name=Size Value \
  $M:type=BufferPool,scope=networking,name=OverflowSize Value >> $R/jmx.csv 2>> $R/jmx.err &
wait
