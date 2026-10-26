#!/usr/bin/env bash
# Instrument check of collector.btm (not a reading): runs the unit test under the same Byteman rules; the collector IS used there,
# so COLL lines must appear (ctor n>=1, add n >= 1,000,000 because the test feeds >1M adds) and LIVE walker lines too.
# usage: bash instr-check.sh <run-name>   (needs a prior unit-run.sh in the same run-name for tc-env.txt)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-tc}; RUN=${1:-shake}
L=$HOME/s4-b7-tc-logs/$RUN/unit; BM=$C/build/lib/jars/byteman-4.0.20.jar
CLS=CollectorGrowthTest; PK=org.apache.cassandra.io.tries
CP=$(grep '^CP=' "$L/tc-env.txt" | head -1 | cut -c4-); mapfile -t ARGS < <(grep '^ARG=' "$L/tc-env.txt" | cut -c5- | grep -v -e '^-Xmx' -e '^-Xms')
mkdir -p $C/test/unit/org/apache/cassandra/io/tries; 
rm -f $L/instr.trace
cd $C && java -Xmx512m "${ARGS[@]}" -javaagent:$BM=script:$H/collector.btm -Dstage4.trace=$L/instr.trace -Dtc.tag=instr -Dtc.out=$L/tc-instr.txt -cp "$CP" org.junit.runner.JUnitCore $PK.$CLS > $L/instr.log 2>&1 < /dev/null
echo "junit exit $? $(grep -m1 -E '^OK|^Tests run' $L/instr.log)"
echo "trace lines: $(wc -l < $L/instr.trace)  max ctor n: $(grep 'COLL ctor' $L/instr.trace | sed 's/.*n=\([0-9]*\).*/\1/' | sort -n | tail -1)  max add n: $(grep 'COLL add' $L/instr.trace | sed 's/.*n=\([0-9]*\).*/\1/' | sort -n | tail -1)  max walker n: $(grep 'LIVE walker' $L/instr.trace | sed 's/.*n=\([0-9]*\).*/\1/' | sort -n | tail -1)"
grep -c 'LIVE saireader\|LIVE valueiterator' $L/instr.trace | sed 's/^/sai+valueiterator lines: /'
