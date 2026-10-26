#!/bin/bash
# Instrument check, not a reading. Usage: bash instrument-check.sh <tree> <helper-jar> <outdir> <classes-dir>
# <classes-dir> holds the javac-compiled PathBufferSizeTest. Runs PathBufferSizeTest.main (known-answer cells) under the Byteman agent with tp.btm, and prints the PROBE lines and the helper's events.
set -u
T=$1; HJ=$2; OUT=$3; TC=$4; HARN=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT; rm -f $OUT/tp-*.txt
BM=$T/build/lib/jars/byteman-4.0.20.jar
OPTS=$(grep -v '^#' $T/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
CP="$TC:$T/build/test/lib/jars/*:$T/build/classes/main:$T/build/lib/jars/*"
echo check > $OUT/tp-phase.txt
java $OPTS -javaagent:$T/build/lib/jars/jamm-0.4.0.jar -javaagent:$BM=listener:false,boot:$BM,boot:$HJ,script:$HARN/tp.btm -Dstage4.tp.events=$OUT/tp-events.txt -Dstage4.tp.stats=$OUT/tp-stats.txt -Dstage4.tp.phase=$OUT/tp-phase.txt -cp "$CP" org.apache.cassandra.db.tries.PathBufferSizeTest > $OUT/main.out 2>&1
echo "exit $?"; grep -a "^PROBE\|^RESULT\|Byteman\|Exception\|rror" $OUT/main.out | head -30; echo "--- events:"; cat $OUT/tp-events.txt; sleep 3; echo "--- stats:"; cat $OUT/tp-stats.txt
