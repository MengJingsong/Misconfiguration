#!/usr/bin/env bash
# R8 sampler on pc91 (from S2 run-2 sample.sh): ONE S2Poll JVM (-Xmx48m) on V's JMX (7199), 1 s interval, until V dies.
# Started by arm.sh with nice -n 10, pinned to 1-31:2.   sample.sh <outdir>
W=/mydata/s4/r8-w1; O=$1; P=$(cat $W/inst/V/cass.pid); CG=$(cat $W/inst/V/cgroup); mkdir -p "$O"
while kill -0 "$P" 2>/dev/null; do
  java -Xmx48m -cp $W/cls S2Poll 1000 "$CG" >> "$O/poll.log" 2>>"$O/poll.err"
  sleep 1
done
echo "$(date +%s) DEAD" >> "$O/poll.log"
