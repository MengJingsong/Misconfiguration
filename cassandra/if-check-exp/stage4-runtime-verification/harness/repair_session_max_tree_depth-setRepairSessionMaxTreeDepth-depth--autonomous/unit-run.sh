#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-25) of repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.
# usage: unit-run.sh <run-label>      e.g. unit-run.sh r1   (run three times: r1, r2, r3)
# Copies TreeDepthSetterTest.java into the run clone, runs `ant testsome` once, and copies the JUnit XML and the test log.
# Output: $W/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/unit-<label>/ (commands.log, summary.txt,
#         ant.log, TEST-*.xml, TEST-*.log, stdout.txt = the test's printed lines, read from the test log)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run24
LAB=${1:?label}
CLS=org.apache.cassandra.repair.TreeDepthSetterTest
L=$W/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/TreeDepthSetterTest.java" "$C/test/unit/org/apache/cassandra/repair/" && echo "+ cp TreeDepthSetterTest.java -> clone" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/TreeDepthSetterTest.java" | cut -c1-12)"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
python3 - "$L" <<'PY'
# Runbook fix 2026-10-25 (defect 1): System.out goes to the logger, so the lines are read from the test log; a printf
# arrives as one INFO line per format piece and is joined.
import glob, re, sys
L = sys.argv[1]
msgs = []
for f in glob.glob(L + '/TEST-*.log'):
    for l in open(f, errors='replace'):
        m = re.match(r'INFO  \[main\] \S+ (.*)$', l.rstrip('\n'))
        if m: msgs.append(m.group(1))
keep, i = [], 0
while i < len(msgs):
    t = msgs[i]
    if t == 'd=' and i + 5 < len(msgs):
        keep.append(''.join(msgs[i:i + 6])); i += 6; continue
    if t.startswith(('ACCEPTED', 'REJECTED', 'getter', 'set ', 'control ')):
        keep.append(t)
    i += 1
open(L + '/stdout.txt', 'w').write('\n'.join(keep) + '\n')
PY
say "stdout lines:"; cat "$L/stdout.txt" >> "$S"
say "warn lines in test log: $(grep -h 'could lead to excessive memory usage' "$L"/TEST-*.log 2>/dev/null | grep -c .)"
grep -h 'could lead to excessive memory usage' "$L"/TEST-*.log 2>/dev/null | sed 's/^/  /' >> "$S"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
