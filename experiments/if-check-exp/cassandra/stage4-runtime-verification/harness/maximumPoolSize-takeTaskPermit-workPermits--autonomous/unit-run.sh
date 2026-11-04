#!/usr/bin/env bash
# Unit tier (B2) of maximumPoolSize-takeTaskPermit-workPermits--autonomous (frozen sha256 c004650f…, amendments R2/R4).
# usage: bash unit-run.sh [run-name]      output: ~/stage4-logs/mps/<run-name, default run1>/unit/
# Copies SEPMemoryProbeTest (B2a verbatim + R4's workingMemoryPerRunningTask) into ~/cassandra-mps and runs B2e step 3
# three times (B2e step 5): ant testsome with -Dtest.jvm.args="-Xms2g -Xmx2g -XX:+UseG1GC" (B2e step 3 as fixed by D1: -XX:-UseConcMarkSweepGC -XX:+UseG1GC, no -Xms/-Xmx; ant sets -Xmx1024m) plus a GC log.
# B2e step 4 (grep PROBE in the junit XML) cannot work as written: the test JVM routes System.out through a logger one
# printf argument per line (harness defect H1, found by concurrent_writes); the PROBE lines are rebuilt from the main
# thread's SubstituteLogger fragments in the ant log. unit-analyze.py writes the EXPECTED lines. --remove deletes the test.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-mps}; RUN=${1:-run1}
T=$C/test/unit/org/apache/cassandra/concurrent/SEPMemoryProbeTest.java
if [ "$RUN" = "--remove" ]; then rm -f "$T"; echo "removed $T"; exit 0; fi
L=$HOME/stage4-logs/mps/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SEPMemoryProbeTest.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "git status (B2e step 1): $(git status --short | tr '\n' ' ')"
cp "$H/SEPMemoryProbeTest.java" "$T"
for rep in rep1 rep2 rep3; do
  rm -rf build/test/cassandra build/test/output/TEST-org.apache.cassandra.concurrent.SEPMemoryProbeTest*.xml
  t0=$(date +%s)
  ant testsome -Dtest.name=org.apache.cassandra.concurrent.SEPMemoryProbeTest \
    -Dtest.jvm.args="-XX:-UseConcMarkSweepGC -XX:+UseG1GC -Xlog:gc:file=$L/gc-$rep.log" > "$L/ant-$rep.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-org.apache.cassandra.concurrent.SEPMemoryProbeTest*.xml "$L/TEST-$rep.xml" 2>/dev/null || true
  cp build/test/logs/_jdk11/TEST-org.apache.cassandra.concurrent.SEPMemoryProbeTest.log "$L/test-$rep.log" 2>/dev/null || true
  python3 - "$L/ant-$rep.log" > "$L/$rep.probe" <<'PY'
import re, sys
frag = [m.group(1) for l in open(sys.argv[1], errors='replace')
        for m in [re.search(r' \[main\] \S+ SubstituteLogger\.java:\d+ - (.*?)\n?$', l)] if m]
text = re.sub(r'(PROBE phase=)', r'\n\1', ''.join(frag))
for l in text.splitlines():
    if l.startswith('PROBE phase='):
        print(l.strip())
PY
  say "$rep ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$rep.log") $(( $(date +%s) - t0 )) s; probe lines $(grep -c '^PROBE' "$L/$rep.probe")"
  sed "s/^/  $rep /" "$L/$rep.probe" | tee -a "$S"
done
say "leftover junit JVMs: $(pgrep -u "$(id -u)" -f 'junit.*SEPMemoryProbeTest' | wc -l)"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
