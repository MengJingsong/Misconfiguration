#!/usr/bin/env bash
# R25 (copied from R19, paths /mydata/r25, R1 on ms0640; 2026-11-24). R19 sampler (R11 sample.sh, paths only), runs ON a server node (nice 10): ONE S2Poll JVM (-Xmx48m) on the local JMX (7199), 1 s, until the local
# Cassandra dies or the sampler is killed (from R8/S2 run-2 sample.sh).   sample.sh <outdir> <role>
W=/mydata/r25; O=$1; N=$2; P=$(cat $W/inst/$N/cass.pid); CG=$(cat $W/inst/$N/cgroup); mkdir -p "$O"
while kill -0 "$P" 2>/dev/null; do
  java -Xmx48m -cp $W/cls S2Poll 1000 "$CG" >> "$O/poll.log" 2>>"$O/poll.err"
  sleep 1
done
echo "$(date +%s) DEAD" >> "$O/poll.log"
