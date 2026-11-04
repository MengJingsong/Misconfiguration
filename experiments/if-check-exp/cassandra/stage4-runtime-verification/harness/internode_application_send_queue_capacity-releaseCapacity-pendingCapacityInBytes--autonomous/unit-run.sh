#!/usr/bin/env bash
# Unit tier (B2) of internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.
# usage (on the run node): bash unit-run.sh <run> [base|probe|mutants|all]
#   base    B2e step 2: ConnectionTest#testAcquireReleaseOutbound,testInsufficientSpace (must pass)
#   probe   B2e steps 3-4: SendQueueCapacityProbeTest three times (heap-delta stability)
#   mutants amendment A2: M1 (:451-452 releases `bytes`) and M2 (guard at :449 removed) in a separate clone
#           ~/cassandra-sq2-mut (cloned from the run clone, removed at the end); u1Accounting only; each must show a
#           MISMATCH line or an exception
# Output: ~/stage4-logs/sq2/<run>/unit/{ant-*.log,probe-<i>.out,mut-<M>.out,summary.txt}. Every command is echoed to
# summary.txt with its result.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-sq2}
RUN=${1:?run}; MODE=${2:-all}; L=$HOME/stage4-logs/sq2/$RUN/unit; mkdir -p "$L"
T=org.apache.cassandra.net.SendQueueCapacityProbeTest
say() { echo "$(date -u +%FT%T.%3NZ) $*" | tee -a "$L/summary.txt"; }
res() { local log=$1; echo "rc=$2; $(grep -m1 -E 'Tests run' "$log" | sed 's/^ *\[junit-timeout\] *//' || echo 'no Tests run line'); BUILD FAILED x$(grep -c 'BUILD FAILED' "$log")"; }
say "unit-run.sh $RUN $MODE; clone $C $(git -C "$C" rev-parse --short HEAD) $(git -C "$C" describe --tags); harness md5 $(md5sum "$H/SendQueueCapacityProbeTest.java" | cut -c1-12)"
cp "$H/SendQueueCapacityProbeTest.java" "$C/test/unit/org/apache/cassandra/net/"
cd "$C"
if [ "$MODE" = base ] || [ "$MODE" = all ]; then
  say "ant testsome ConnectionTest -Dtest.methods=testAcquireReleaseOutbound,testInsufficientSpace"
  ant testsome -Dtest.name=org.apache.cassandra.net.ConnectionTest -Dtest.methods=testAcquireReleaseOutbound,testInsufficientSpace </dev/null > "$L/ant-ConnectionTest.log" 2>&1
  say "  ConnectionTest: $(res "$L/ant-ConnectionTest.log" $?)"
fi
if [ "$MODE" = probe ] || [ "$MODE" = all ]; then
  for i in 1 2 3; do
    rm -f "$L/probe-$i.out"
    say "ant testsome $T (repetition $i)"
    mkdir -p "$L/histo-$i"
    ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dstage4.out=$L/probe-$i.out -Dstage4.histo=$L/histo-$i" </dev/null > "$L/ant-probe-$i.log" 2>&1
    say "  probe $i: $(res "$L/ant-probe-$i.log" $?); MISMATCH lines $(grep -c MISMATCH "$L/probe-$i.out"); check lines $(grep -c '^STAGE4 check' "$L/probe-$i.out")"
  done
fi
if [ "$MODE" = mutants ] || [ "$MODE" = all ]; then
  M=$HOME/cassandra-sq2-mut; F=src/java/org/apache/cassandra/net/OutboundConnection.java
  rm -rf "$M"; git clone -q --no-hardlinks "$C" "$M" && git -C "$M" checkout -q cassandra-5.0.9
  cp -r "$C/build" "$M/build"     # reuse the compiled tree; the mutant's build-test recompiles the changed file
  cp "$H/SendQueueCapacityProbeTest.java" "$M/test/unit/org/apache/cassandra/net/"
  for mut in M1 M2; do
    git -C "$M" checkout -q -- $F
    if [ $mut = M1 ]; then sed -i '452s/reserveCapacityInBytes.release(excess);/reserveCapacityInBytes.release(bytes);/' "$M/$F"
    else sed -i '449s/if (pendingBytes(prev) > pendingCapacityInBytes)/if (true)/' "$M/$F"; fi
    git -C "$M" diff -- $F > "$L/mut-$mut.diff"
    say "mutant $mut diff: $(grep -c '^[-+] ' "$L/mut-$mut.diff") changed lines: $(grep '^+ ' "$L/mut-$mut.diff" | tr -s ' ')"
    [ "$(grep -c '^+ ' "$L/mut-$mut.diff")" = 1 ] || { say "  mutant $mut not applied; stop"; exit 1; }
    # runbook defect 1 (2026-10-21): Ant's javac compares mtimes with a 1 s granularity, so a source edited within 1 s of
    # the copied class file was not recompiled (attempt 1's M1 ran unmutated code); delete the class files instead
    rm -f "$M"/build/classes/main/org/apache/cassandra/net/OutboundConnection*.class; touch "$M/$F"
    ( cd "$M" && ant build-test </dev/null > "$L/ant-build-$mut.log" 2>&1 ); say "  build $mut: rc=$? $(grep -c 'BUILD SUCCESSFUL' "$L/ant-build-$mut.log") BUILD SUCCESSFUL"
    rm -f "$L/mut-$mut.out"
    ( cd "$M" && ant testsome -Dtest.name=$T -Dtest.methods=u1Accounting -Dtest.jvm.args="-Dstage4.out=$L/mut-$mut.out" </dev/null > "$L/ant-mut-$mut.log" 2>&1 )
    say "  mutant $mut bytecode at releaseCapacity: $(javap -c -p -cp "$M/build/classes/main" org.apache.cassandra.net.OutboundConnection | sed -n '/void releaseCapacity(long, long)/,/return/p' | grep -B1 'EndpointAndGlobal.release' | head -1 | tr -s ' ')"
    say "  mutant $mut u1Accounting: $(res "$L/ant-mut-$mut.log" $?); MISMATCH lines $(grep -c MISMATCH "$L/mut-$mut.out" 2>/dev/null); exceptions in log: $(grep -m3 -oE '(java\.lang\.[A-Za-z]*Error|[A-Za-z.]*Exception)[^ ]*' "$L/ant-mut-$mut.log" | sort -u | tr '\n' ' ')"
  done
  rm -rf "$M"; say "mutant clone removed"
fi
rm -f "$C/test/unit/org/apache/cassandra/net/SendQueueCapacityProbeTest.java"
say "done"
