#!/usr/bin/env bash
# Unit tier (B2) of concurrent_writes-takeWorkPermit-workPermits--autonomous (audit amendment R6: M = 4000 twice).
# usage (on the run node): unit-run.sh [run-name]          output: ~/stage4-logs/sep/<run-name, default run1>/unit/
# Copies SEPQueueHeapProbeTest into the clone's test/unit/org/apache/cassandra/concurrent/ and runs it with ant testsome
# three times (B2e steps 2-3): rep1 M = 4000, rep2 M = 4000, m8000 M = 8000 (-Dprobe.tasks). Each run's PROBE / SUPPL
# lines are taken from the junit XML (system-out, B2e step 4) into <rep>.probe; summary.txt lists them; unit-analyze.py
# then writes the B2f/B2g EXPECTED lines. The test JVM heap is build.xml's 4G default (B2a). The test file stays in the
# clone (untracked); remove it with unit-run.sh --remove.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-sep}; RUN=${1:-run1}
T=$C/test/unit/org/apache/cassandra/concurrent/SEPQueueHeapProbeTest.java
if [ "$RUN" = "--remove" ]; then rm -f "$T"; echo "removed $T"; exit 0; fi
L=$HOME/stage4-logs/sep/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SEPQueueHeapProbeTest.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/SEPQueueHeapProbeTest.java" "$T"
for spec in rep1:4000 rep2:4000 m8000:8000; do
  rep=${spec%%:*}; m=${spec#*:}
  rm -rf build/test/cassandra build/test/output/TEST-org.apache.cassandra.concurrent.SEPQueueHeapProbeTest*.xml
  t0=$(date +%s)
  ant testsome -Dtest.name=org.apache.cassandra.concurrent.SEPQueueHeapProbeTest \
    -Dtest.jvm.args="-Dprobe.tasks=$m -Xlog:gc:file=$L/gc-$rep.log" > "$L/ant-$rep.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-org.apache.cassandra.concurrent.SEPQueueHeapProbeTest*.xml "$L/TEST-$rep.xml" 2>/dev/null || true
  cp build/test/logs/_jdk11/TEST-org.apache.cassandra.concurrent.SEPQueueHeapProbeTest.log "$L/test-$rep.log" 2>/dev/null || true
  # the test JVM routes System.out through a logger one printf argument per line (SubstituteLogger.java:222, harness
  # defect H1; only System.out goes through SubstituteLogger, as the ant log shows): join the main thread's fragments and split at each PROBE / SUPPL
  python3 - "$L/ant-$rep.log" > "$L/$rep.probe" <<'PY'
import re, sys
frag = [m.group(1) for l in open(sys.argv[1], errors='replace')
        for m in [re.search(r' \[main\] \S+ SubstituteLogger\.java:\d+ - (.*?)\n?$', l)] if m]
text = re.sub(r'(PROBE n=|SUPPL idle )', r'\n\1', ''.join(frag))
for l in text.splitlines():
    if l.startswith(('PROBE n=', 'SUPPL idle ')):
        print(l.strip())
PY
  say "$rep M=$m ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$rep.log") $(( $(date +%s) - t0 )) s; probe lines $(grep -c '^PROBE' "$L/$rep.probe")"
  sed "s/^/  $rep /" "$L/$rep.probe" | tee -a "$S"
done
say "leftover junit JVMs: $(pgrep -u "$(id -u)" -f 'junit.*SEPQueueHeapProbeTest' | wc -l)"
python3 "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
