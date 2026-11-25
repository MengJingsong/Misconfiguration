#!/usr/bin/env bash
# One sample (B3d + A6b). Usage: sample.sh <label> <client-pid or -> <dn-pid> ; prints KEY=VALUE lines prefixed "S <label>".
# Env: JAVA_HOME. Client part skipped when client pid is "-".
LBL=$1; CPID=$2; DNPID=$3
J=$JAVA_HOME/bin
p() { echo "S $LBL $*"; }
p "time=$(date +%s.%N)"
if [ "$CPID" != "-" ] && [ -d /proc/$CPID ]; then
  p "client_estab_9866=$(ss -tnp state established '( dport = :9866 )' | grep -c "pid=$CPID,")"
  p "client_fd=$(ls /proc/$CPID/fd | wc -l)"
  $J/jcmd $CPID GC.run > /dev/null 2>&1
  G=$($J/jstat -gc $CPID | tail -1)
  p "client_jstat_gc=$(echo $G | tr ' ' ',')"
  p "client_heap_used_bytes=$(echo $G | awk '{printf "%.0f", ($3+$4+$6+$8)*1024}')"
  $J/jcmd $CPID GC.class_histogram 2>/dev/null | grep -E 'NioInetPeer|SocketChannelImpl|PeerCache\$|LinkedListMultimap\$Node' | while read -r l; do p "client_histo $l"; done
  N=$($J/jcmd $CPID VM.native_memory summary 2>/dev/null)
  p "client_nmt_total $(echo "$N" | grep -m1 '^Total:')"
  p "client_nmt_internal $(echo "$N" | grep -m1 -- '- *Internal (')"
  p "client_nmt_thread $(echo "$N" | grep -m1 -- '- *Thread (')"
  p "client_rss_kb=$(awk '/VmRSS/{print $2}' /proc/$CPID/status)"
  p "client_skmem_sockets=$(ss -tmn state established '( dport = :9866 )' | grep -c skmem)"
fi
p "dn_xceivercount=$(curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | grep -o '"XceiverCount" *: *[0-9]*' | grep -o '[0-9]*$')"
p "dn_dataxceiver_threads=$($J/jcmd $DNPID Thread.print 2>/dev/null | grep -c '^"DataXceiver')"
p "dn_nmt_thread $($J/jcmd $DNPID VM.native_memory summary 2>/dev/null | grep -m1 -- '- *Thread (')"
p "dn_rss_kb=$(awk '/VmRSS/{print $2}' /proc/$DNPID/status)"
p "dn_estab_from_9866=$(ss -tn state established '( sport = :9866 )' | tail -n +2 | wc -l)"
