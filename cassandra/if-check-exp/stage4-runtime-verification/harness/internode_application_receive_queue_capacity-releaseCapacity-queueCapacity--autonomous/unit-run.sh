#!/usr/bin/env bash
# Unit tier (B2) of internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.
# usage (on the run node): bash unit-run.sh <run> [upstream|harness|mutant|all]     output: ~/stage4-logs/rrc/<run>/unit/
#   upstream  ResourceLimitsTest (the reserve primitive; a control that the clone's tests run)
#   harness   ReleaseCapacityProbeTest (B2c/B2e steps 1-3: script, boundary, throttled, reactivation, concurrent x5,
#             defaults), then ReleaseCapacityConfigTest (B2b 8 MiB) in its own `ant testsome` (its own JVM)
#   mutant    B2e step 4 as amended by R1, in a separate fresh clone ~/cassandra-rrc-mut (never in the run clone):
#             M1 = release `bytes` instead of `excess` when the guard is true; M2 = guard removed (`if (true)`);
#             both must make ReleaseCapacityProbeTest fail. M0 = the filed `>=` mutant, run only to record R1's
#             audit finding (expected to pass: an equivalent mutant). The file is reverted after each and the clone
#             removed at the end.
# The tests are copied into the run clone's test/unit/org/apache/cassandra/net/ and removed again at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
RUN=${1:?run name}; what=${2:-all}
L=$HOME/stage4-logs/rrc/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; [ "$what" = all ] && : > "$S"
T=test/unit/org/apache/cassandra/net
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse --short HEAD) md5 $(cd "$H" && md5sum ReleaseCapacityProbeTest.java ReleaseCapacityConfigTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
run() {   # run <clone> <class> <logname> [extra ant args...]
  local cl=$1 cls=$2 name=$3; shift 3
  ( cd "$cl" && rm -rf build/test/cassandra && ant testsome -Dtest.name=$cls "$@" > "$L/$name.ant.log" 2>&1 < /dev/null )
  local rc=$?
  cp "$cl"/build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$name $cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$name.ant.log") $(grep -m1 -o 'BUILD [A-Z]*' "$L/$name.ant.log")"
  return $rc
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run "$C" org.apache.cassandra.net.ResourceLimitsTest upstream-ResourceLimitsTest
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  cp "$H/ReleaseCapacityProbeTest.java" "$H/ReleaseCapacityConfigTest.java" "$C/$T/"
  rm -f "$L/harness.out"
  run "$C" org.apache.cassandra.net.ReleaseCapacityProbeTest probe -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  run "$C" org.apache.cassandra.net.ReleaseCapacityConfigTest config -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out") MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out")"
  grep 'MISMATCH' "$L/harness.out" | tee -a "$S"
  grep '^STAGE4 method\|^STAGE4 summary' "$L/harness.out" | tee -a "$S"
  rm -f "$C/$T/ReleaseCapacityProbeTest.java" "$C/$T/ReleaseCapacityConfigTest.java"
fi
if [ "$what" = mutant ] || [ "$what" = all ]; then
  M=$HOME/cassandra-rrc-mut; F=src/java/org/apache/cassandra/net/AbstractMessageHandler.java
  rm -rf "$M"
  git clone --quiet --branch cassandra-5.0.9 --depth 1 /proj/misconfiguration-PG0/git-repos/cassandra-src "$M" > "$L/mutant-clone.log" 2>&1
  say "mutant clone $(git -C "$M" describe --tags) $(git -C "$M" rev-parse --short HEAD)"
  ( cd "$M" && ant build-test > "$L/mutant-build.log" 2>&1 < /dev/null ); say "mutant clone build-test: $(grep -m1 -o 'BUILD [A-Z]*' "$L/mutant-build.log")"
  cp "$H/ReleaseCapacityProbeTest.java" "$M/$T/"
  mut() {   # mut <name> <python replace: old> <new> <expect pass|fail>
    local name=$1 old=$2 new=$3 want=$4
    git -C "$M" checkout --quiet -- "$F"
    python3 - "$M/$F" "$old" "$new" <<'PY' || { echo "patch failed" >&2; return 2; }
import sys
p, old, new = sys.argv[1:4]
s = open(p).read()
assert s.count(old) == 1, (old, s.count(old))
open(p, 'w').write(s.replace(old, new))
PY
    git -C "$M" diff --stat > "$L/mutant-$name.diff"; git -C "$M" diff >> "$L/mutant-$name.diff"
    rm -f "$L/mutant-$name.out"
    run "$M" org.apache.cassandra.net.ReleaseCapacityProbeTest mutant-$name -Dtest.jvm.args="-Dstage4.out=$L/mutant-$name.out"
    local rc=$?
    local res=pass; [ $rc -ne 0 ] && res=fail
    say "MUTANT $name: tests $res (expected $want); failing methods: $(grep -o 'STAGE4 method [a-z]* mismatches=[1-9][0-9]*' "$L/mutant-$name.out" | awk '{print $3}' | tr '\n' ' ') errors: $(grep -c '<error' "$M"/build/test/output/TEST-org.apache.cassandra.net.ReleaseCapacityProbeTest*.xml 2>/dev/null) $(grep -o -m3 'UnrecoverableIllegalStateException\|AssertionError' "$L/mutant-$name.ant.log" | sort | uniq -c | tr '\n' ' ')"
    git -C "$M" checkout --quiet -- "$F"
  }
  mut M1 'long excess = min(oldQueueSize - queueCapacity, bytes);' 'long excess = bytes; // STAGE4 MUTANT M1' fail
  mut M2 'if (oldQueueSize > queueCapacity)' 'if (true) // STAGE4 MUTANT M2 (guard removed)' fail
  mut M0 'if (oldQueueSize > queueCapacity)' 'if (oldQueueSize >= queueCapacity) // STAGE4 MUTANT M0 (filed, equivalent per R1)' pass
  say "mutant clone reverted: diff lines $(git -C "$M" diff | wc -l)"
  rm -rf "$M"; say "mutant clone removed: $([ -d "$M" ] && echo no || echo yes)"
fi
say "unit-run $what end $(date -Is)"
