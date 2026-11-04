#!/usr/bin/env bash
# Unit tier (B2 + B2i) of max-unsigned-short-validate-key-remaining--autonomous.
# usage: unit-run.sh [run-name]   (default run1)     output: ~/s4-b8-uk-logs/<run>/unit/
# Compiles KeyLenDriver outside the tree, runs bounds / stream / hold (L=65535, then L=1 control) in separate JVMs (-Xmx1g),
# writes summary.txt with EXPECTED: lines. Stops at the first failed first-trigger check (the boundary).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); T=${CASSANDRA_HOME:-$HOME/s4-b8-uk/u}; RUN=${1:-run1}
L=$HOME/s4-b8-uk-logs/$RUN/unit; mkdir -p "$L/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$T/build/classes/main:$T/build/lib/jars/*:$T/conf"
JOPT="-Xmx1g -Xss4m -Dcassandra.config=file://$T/conf/cassandra.yaml -Dcassandra.storagedir=$L/storage -Dlogback.configurationFile=$T/conf/logback.xml -Dcassandra.logdir=$L/logs"
JOPT="$JOPT --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
say "unit-run $(date -Is) host $(hostname -s) tree $(git -C "$T" describe --tags) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum KeyLenDriver.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$L/classes" -cp "$CP" "$H/KeyLenDriver.java" > "$L/javac.log" 2>&1 || { say "COMPILE FAILED"; cat "$L/javac.log" | tee -a "$S"; exit 1; }
run() { local name=$1; shift
  java $JOPT -cp "$L/classes:$CP" KeyLenDriver "$@" > "$L/$name.out" 2> "$L/$name.err"; local rc=$?
  say "run $name ($*) exit $rc, $(grep -c '^STAGE4 check' "$L/$name.out") checks, $(grep -c 'MISMATCH' "$L/$name.out") MISMATCH"
  return $rc; }
run bounds bounds || { say "FAILED: bounds (see $L/bounds.err)"; tail -5 "$L/bounds.err" | tee -a "$S"; exit 1; }
if grep -q MISMATCH "$L/bounds.out"; then
  say "EXPECTED: boundary 0/1/1000/65534/65535 accepted and 65536/70000/1000000 rejected with the exact message - NO (first-trigger check failed; stopping)"; grep MISMATCH "$L/bounds.out" | tee -a "$S"; exit 1
else say "EXPECTED: boundary 0/1/1000/65534/65535 accepted and 65536/70000/1000000 rejected with the exact message - yes"; fi
run stream stream 100000 65535 || { say "FAILED: stream"; tail -5 "$L/stream.err" | tee -a "$S"; exit 1; }
run hold65535 hold 65535 || { say "FAILED: hold65535"; tail -5 "$L/hold65535.err" | tee -a "$S"; exit 1; }
run hold1 hold 1 || { say "FAILED: hold1"; tail -5 "$L/hold1.err" | tee -a "$S"; exit 1; }
for f in stream hold65535 hold1; do grep -q MISMATCH "$L/$f.out" && say "EXPECTED: $f checks - NO" || say "EXPECTED: $f checks - yes"; done
python3 - "$L" <<'PY' | tee -a "$S"
import re,sys
L=sys.argv[1]
def slope(f):
    m=re.search(r'slope_bytes_per_key=([\d.]+)',open(f'{L}/{f}.out').read()); return float(m.group(1))
s1,s2=slope('hold1'),slope('hold65535')
print(f'slope L=1: {s1:.1f} B/key; L=65535: {s2:.1f} B/key; ratio {s2/s1:.0f}')
print('EXPECTED: slope ratio above 500 - ' + ('yes' if s2/s1>500 else 'NO'))
PY
say "done $(date -Is)"
