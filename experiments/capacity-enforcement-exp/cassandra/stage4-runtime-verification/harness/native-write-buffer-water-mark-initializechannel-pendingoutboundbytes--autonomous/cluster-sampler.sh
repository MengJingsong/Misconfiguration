#!/bin/bash
# usage: cluster-sampler.sh <pid> <outfile> ; every 2 s: epoch_ms otherCommittedKB rssKB serverSendQ clientRecvQ
PID=$1; OUT=$2
echo "# ts_ms other_committed_KB rss_KB server_sendq client_recvq" > $OUT
while kill -0 $PID 2>/dev/null; do
  ts=$(date +%s%3N)
  oth=$(jcmd $PID VM.native_memory summary 2>/dev/null | grep -E '^-\s+Other \(' | sed -E 's/.*committed=([0-9]+)KB.*/\1/')
  rss=$(awk '/VmRSS/{print $2}' /proc/$PID/status)
  sq=$(ss -tn 'sport = :19142' | awk 'NR>1{s+=$3} END{print s+0}')
  rq=$(ss -tn 'dport = :19142' | awk 'NR>1{s+=$2} END{print s+0}')
  echo "$ts ${oth:-NA} $rss $sq $rq" >> $OUT
  sleep 2
done
