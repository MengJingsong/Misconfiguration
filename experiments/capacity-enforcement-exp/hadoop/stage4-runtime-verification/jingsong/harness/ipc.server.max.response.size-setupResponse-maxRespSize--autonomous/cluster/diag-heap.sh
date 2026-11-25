#!/usr/bin/env bash
# Supplementary diagnostic (NOT part of the B3e runbook), 2026-11-25: run 1 read old-gen "used" after
# GC.run of 51528K at K=64 MiB vs ~47490K at the other K values (B3f predicted equal within 5 %).
# Repeats the 20-ls loop for K = 64 MiB, 1024, 64 MiB on the same namespace and records the heap
# and the top of the class histogram after GC.run, to see whether the difference follows K.
# Runs ON pc91. Usage: diag-heap.sh <RUN dir>
set -uo pipefail
RUN=${1:?RUN}
J11=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf JAVA_HOME=$J11 PATH=$RUN/hadoop/bin:$J11/bin:$PATH
OUT=$RUN/cluster-out/diag; mkdir -p $OUT
exec > >(tee -a $OUT/diag-heap.log) 2>&1
die() { echo "STOP: $*"; exit 2; }
setk() { sed -i "s|<name>ipc.server.max.response.size</name><value>[0-9]*</value>|<name>ipc.server.max.response.size</name><value>$1</value>|" $RUN/conf/core-site.xml
         grep -o '<name>ipc.server.max.response.size</name><value>[0-9]*</value>' $RUN/conf/core-site.xml; }
echo "== $(date)"
hdfs --daemon start datanode || die dn
i=0
for K in 67108864 1024 67108864; do
  i=$((i+1)); L=d$i-K$K
  echo "==== $L $(date)"; setk $K
  hdfs --daemon stop namenode 2>/dev/null; sleep 2
  hdfs --daemon start namenode || die nn
  hdfs dfsadmin -safemode wait 2>/dev/null
  P=$(cat $RUN/pids/hadoop-*-namenode.pid)
  for j in $(seq 20); do printf '%s ' "$(hdfs dfs -ls /big 2>/dev/null | wc -l)"; done; echo
  jcmd $P GC.run > /dev/null
  jcmd $P GC.heap_info | grep 'garbage-first heap'
  jcmd $P GC.class_histogram | head -14 > $OUT/histo-$L.txt; cat $OUT/histo-$L.txt
  jcmd $P Thread.print > $OUT/threads-$L.txt
done
hdfs --daemon stop namenode; hdfs --daemon stop datanode; sleep 3
echo "leftover:"; ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode' | cut -c1-150 || echo none
echo "== done $(date)"
