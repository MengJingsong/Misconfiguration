#!/usr/bin/env bash
# Unit tier (B2 + B2i) of max-unsigned-short-validate-sum--autonomous.
# usage: unit-run.sh [run-name]   (default run1)     output: ~/s4-b9-cs-logs/<run>/unit/
# Compiles ClusterKeyDriver outside the tree, runs grid / stream / series (S=65535 three times, S=16, capped) in separate JVMs (-Xmx3g),
# writes summary.txt with EXPECTED: lines. Stops at the first failed first-trigger check (the grid boundary).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); T=${CASSANDRA_HOME:-$HOME/s4-b9-cs}; RUN=${1:-run1}
L=$HOME/s4-b9-cs-logs/$RUN/unit; mkdir -p "$L/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$T/build/classes/main:$T/build/lib/jars/*:$T/conf"
JOPT="-Xmx3g -Xss4m -Dcassandra.config=file://$T/conf/cassandra.yaml -Dcassandra.storagedir=$L/storage -Dlogback.configurationFile=$T/conf/logback.xml -Dcassandra.logdir=$L/logs"
JOPT="$JOPT --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
say "unit-run $(date -Is) host $(hostname -s) tree $(git -C "$T" describe --tags) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum ClusterKeyDriver.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$L/classes" -cp "$CP" "$H/ClusterKeyDriver.java" > "$L/javac.log" 2>&1 || { say "COMPILE FAILED"; cat "$L/javac.log" | tee -a "$S"; exit 1; }
run() { local name=$1; shift
  java $JOPT -cp "$L/classes:$CP" ClusterKeyDriver "$@" > "$L/$name.out" 2> "$L/$name.err"; local rc=$?
  say "run $name ($*) exit $rc, $(grep -c '^STAGE4 check' "$L/$name.out") checks, $(grep -c 'MISMATCH' "$L/$name.out") MISMATCH"
  return $rc; }
run grid grid || { say "FAILED: grid (see $L/grid.err)"; tail -5 "$L/grid.err" | tee -a "$S"; exit 1; }
if grep -q MISMATCH "$L/grid.out"; then
  say "EXPECTED: S x N grid and mixed cells accepted/rejected with the exact message of B2i.2 - NO (first-trigger check failed; stopping)"; grep MISMATCH "$L/grid.out" | tee -a "$S"; exit 1
else say "EXPECTED: S x N grid and mixed cells accepted/rejected with the exact message of B2i.2 - yes"; fi
run stream stream 100000 32768 32767 || { say "FAILED: stream"; tail -5 "$L/stream.err" | tee -a "$S"; exit 1; }
for n in a b c; do run big$n series 32768 32767 1000 0 || { say "FAILED: big$n"; tail -5 "$L/big$n.err" | tee -a "$S"; exit 1; }; done
run small series 8 8 10000 0 || { say "FAILED: small"; tail -5 "$L/small.err" | tee -a "$S"; exit 1; }
run capped series 32768 32767 1000 2000 || { say "FAILED: capped"; tail -5 "$L/capped.err" | tee -a "$S"; exit 1; }
for f in stream biga bigb bigc small capped; do grep -q MISMATCH "$L/$f.out" && say "EXPECTED: $f checks - NO" || say "EXPECTED: $f checks - yes"; done
python3 - "$L" <<'PY' | tee -a "$S"
import re,sys
L=sys.argv[1]
def get(f,k):
    return float(re.search(k+r'=(-?[\d.]+)',open(f'{L}/{f}.out').read()).group(1))
s=[get(f'big{x}','slope_bytes_per_key') for x in 'abc']; s1=get('small','slope_bytes_per_key')
print('slopes S=65535 (3 JVMs): '+', '.join(f'{x:.1f}' for x in s)+f'; S=16: {s1:.1f}; ratio {min(s)/s1:.1f}')
print('EXPECTED: three S=65535 slopes agree within 5 percent - '+('yes' if (max(s)-min(s))/min(s)<0.05 else 'NO'))
print('EXPECTED: S=16 slope below 600 B per key and S=65535 over S=16 above 100 - '+('yes' if s1<600 and min(s)/s1>100 else 'NO'))
d=get('biga','delta_3_to_10')
print(f'uncapped delta M=3000->10000 {d:.0f}'+'; EXPECTED: uncapped growth above 400 MB - '+('yes' if d>400e6 else 'NO'))
PY
say "done $(date -Is)"
