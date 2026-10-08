#!/usr/bin/env bash
# Unit tier of internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes (case 9c/9e):
# copies the two harness tests into the local clone and runs the three upstream controls and the two harness classes, one ant call each
# (SendQueueWiringTest in its own JVM, as it must be). With "instrument" as the first argument it instead runs SendQueueCapacityTest alone with
# send-config.btm and send-acquire.btm attached (the instrument check of 9e "Before the cluster tier", step 1).
# usage (on the measured node): unit-run.sh [instrument|<suffix>]     output: ~/stage4-logs/ssq/unit[-suffix]/{run.out,ant-<class>.log,summary.txt}
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
MODE=${1:-}; L=$HOME/stage4-logs/ssq/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L"/run.out "$L"/summary.txt "$L"/send-trace.txt
cp "$H/SendQueueCapacityTest.java" "$H/SendQueueWiringTest.java" "$C/test/unit/org/apache/cassandra/net/"
cd "$C"
if [ "$MODE" = instrument ]; then
  ant testsome -Dtest.name=org.apache.cassandra.net.SendQueueCapacityTest \
    -Dtest.jvm.args="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/send-config.btm,script:$H/send-acquire.btm -Dstage4.byteman.out=$L/send-trace.txt -Dstage4.out=$L/run.out" > "$L/ant-SendQueueCapacityTest.log" 2>&1
  rc=$?
  echo "SendQueueCapacityTest (instrumented): ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-SendQueueCapacityTest.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-SendQueueCapacityTest.log") BUILD FAILED" | tee -a "$L/summary.txt"
  echo "trace lines: config $(grep -c '^config ' "$L/send-trace.txt" 2>/dev/null || echo 0), acquire $(grep -c '^acquire ' "$L/send-trace.txt" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
  exit 0
fi
for t in org.apache.cassandra.net.ConnectionTest#testInsufficientSpace org.apache.cassandra.net.ConnectionTest#testAcquireReleaseOutbound \
         org.apache.cassandra.net.ResourceLimitsTest org.apache.cassandra.net.SendQueueCapacityTest org.apache.cassandra.net.SendQueueWiringTest; do
  cls=${t%%#*}; n=${cls##*.}; opts="-Dtest.name=$cls"; [ "$t" != "$cls" ] && { opts="$opts -Dtest.methods=${t#*#}"; n="$n.${t#*#}"; }
  ant testsome $opts -Dtest.jvm.args="-Dstage4.out=$L/run.out" > "$L/ant-$n.log" 2>&1
  rc=$?
  echo "$n: ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-$n.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-$n.log") BUILD FAILED" | tee -a "$L/summary.txt"
done
echo "MISMATCH lines: $(grep -c MISMATCH "$L/run.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
tail -1 "$L/run.out" 2>/dev/null || true
