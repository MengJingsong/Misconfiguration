#!/usr/bin/env bash
# S2 run 2 sampler, runs ON a server node (nice 10) until its Cassandra dies or the sampler is killed.
#   sample.sh <outdir> <role>
# poll.log: one line every 3 s from ONE long-lived JMX poller JVM (S2Poll, -Xmx48m): heap used/committed (no forced
# GC), MutationStage pending/active/completed, Native-Transport-Requests pending/active, b6.t_blob memtable live /
# on-heap size, hints created / in progress, scope memory.current and memory.swap.current (no memory.peak on 5.15).
# (The first arm, A-2G-r1, used a nodetool/jcmd/cqlsh loop instead: ~30 s per cycle on the loaded m400; shakedown.)
set -uo pipefail
O=$1 N=$2; P=$(cat /mydata/s2r2/inst/$N/cass.pid); CG=$(cat /mydata/s2r2/inst/$N/cgroup); mkdir -p "$O"
while kill -0 "$P" 2>/dev/null; do
  java -Xmx48m -cp /mydata/s2r2/cls S2Poll 3000 "$CG" >> "$O/poll.log" 2>>"$O/poll.err"
  sleep 3
done
echo "$(date +%s) DEAD" >> "$O/poll.log"
