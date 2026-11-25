#!/bin/bash
cd $WORK/src; b="org.apache.cassandra.metrics:type=BufferPool,scope=networking"
echo "== $1 $(date +%s.%N)"
for n in UsedSize Size OverflowSize; do echo "$n $(bin/nodetool sjk mx -b "$b,name=$n" -mg -f Value 2>/dev/null | tail -1)"; done
jcmd $(cat $WORK/cassandra.pid) VM.native_memory summary | grep -E '^-? *Other'
ss -tmn '( sport = :9042 )' | awk 'NR>1{print "srvSendQ", $3}'
ss -tmn '( dport = :9042 )' | awk 'NR>1{print "proxyRecvQ", $2}'
