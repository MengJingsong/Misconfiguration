#!/usr/bin/env bash
# Unit tier (B2) of monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.
# One JVM per repetition and M; inside it the N values 0,1,50,1000,-1 in turn (MonitoringTask.make(3600000, N) each time).
# usage: unit-run.sh [reps]   env A (default ~/s4-base)   output ~/stage4-logs/mon/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); A=${A:-$HOME/s4-base}; L=$HOME/stage4-logs/mon/unit; REPS=${1:-3}
mkdir -p "$L"
cp "$H/MonitoringQueueCapTest.java" "$A/test/unit/org/apache/cassandra/db/monitoring/"
echo "tree $A: $(git -C $A describe --tags) diff: $(git -C $A diff --stat | tail -1)" | tee -a "$L/summary.txt"
run() { # <M> <rep> <ns>
  local lab="m$1-r$2"
  (cd "$A" && ant testsome -Dtest.name=org.apache.cassandra.db.monitoring.MonitoringQueueCapTest \
    -Dtest.jvm.args="-Dstage4.out=$L/run.out -Dstage4.m=$1 -Dstage4.rep=$2 -Dstage4.ns=$3" </dev/null > "$L/ant-$lab.log" 2>&1)
  echo "$lab: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$lab.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"; }
for r in $(seq 1 $REPS); do run 10000 $r 0,1,50,1000,-1; done
run 100000 1 50,1000,-1          # M ten times larger: the cap must not move with M
echo "cells: $(grep -c 'STAGE4 final' "$L/run.out")" | tee -a "$L/summary.txt"
