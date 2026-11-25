#!/usr/bin/env bash
# B28 monitors (identical in every arm). 3-b confirm (2026-11-24): + poller C every 5 s (client/auth metrics). Usage: monitor.sh <pid> <run dir> <stopfile>
# JMX poller A every 500 ms (TracingStage queue/consumer, dropped _TRACE, MutationStage pending, in-flight K, heap used);
# JMX poller B every 2 s (system_traces memtable on-heap bytes); RssAnon + scope memory.current every 2 s;
# Thread.print summary every 10 s (threadcount.py); df + du of commitlog/hints/system_traces every 10 s.
PID=$1; R=$2; STOP=$3; H=$(dirname "$0")
CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$PID/cgroup 2>/dev/null)
echo "cgroup $CG" > $R/monitor-info.txt
T=$(readlink /proc/$PID/cwd)
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    echo "$(date +%s%3N) $(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null) $(cat $CG/memory.current 2>/dev/null)" >> $R/rss.txt
    sleep 2
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    ts=$(date +%s)
    l=$(timeout 15 jcmd $PID Thread.print 2>/dev/null | python3 -I $H/threadcount.py)
    echo "$ts $l" >> $R/threads.txt
    sleep 10
  done ) &
( while kill -0 $PID 2>/dev/null && [ ! -e $STOP ]; do
    echo "$(date +%s) $(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9) $(du -sm $T/data/commitlog $T/data/hints $T/data/data/system_traces 2>/dev/null | awk '{printf "%s ", $1}') $(cut -d' ' -f1-3 /proc/loadavg)" >> $R/df.txt
    sleep 10
  done ) &
M=org.apache.cassandra.metrics
TP="$M:type=ThreadPools,path=internal,scope=TracingStage"
echo "epoch_ms,trace_pending,trace_completed,trace_active,trace_dropped,mutation_pending,requestssize,heap_used" > $R/jmx.csv
java -cp $H Jmx 7199 poll 500 1000000 $STOP \
  "$TP,name=PendingTasks" Value "$TP,name=CompletedTasks" Value "$TP,name=ActiveTasks" Value \
  "$M:type=DroppedMessage,scope=_TRACE,name=Dropped" Count \
  "$M:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks" Value \
  "$M:type=Client,name=RequestsSize" Value \
  java.lang:type=Memory HeapMemoryUsage >> $R/jmx.csv 2>> $R/jmx.err &
echo "epoch_ms,sessions_onheap,events_onheap" > $R/jmx-mt.csv
java -cp $H Jmx 7199 poll 2000 1000000 $STOP \
  "$M:type=Table,keyspace=system_traces,scope=sessions,name=AllMemtablesOnHeapDataSize" Value \
  "$M:type=Table,keyspace=system_traces,scope=events,name=AllMemtablesOnHeapDataSize" Value >> $R/jmx-mt.csv 2>> $R/jmx.err &
echo "epoch_ms,connected,auth_success,auth_failure,protocol_exc,ntr_active,ntr_pending" > $R/jmx-client.csv
java -cp $H Jmx 7199 poll 5000 1000000 $STOP \
  "$M:type=Client,name=ConnectedNativeClients" Value "$M:type=Client,name=AuthSuccess" Count \
  "$M:type=Client,name=AuthFailure" Count "$M:type=Client,name=ProtocolException" Count \
  "$M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=ActiveTasks" Value \
  "$M:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks" Value >> $R/jmx-client.csv 2>> $R/jmx.err &
wait
