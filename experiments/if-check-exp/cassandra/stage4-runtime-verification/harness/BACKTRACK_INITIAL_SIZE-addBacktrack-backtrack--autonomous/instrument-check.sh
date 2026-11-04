#!/bin/bash
# Instrument check (B3i.5), not a reading. Usage: bash instrument-check.sh <tree> <helper-jar> <classes-dir(test)> <junit-jar> <outdir>
# Runs BacktrackSizeTest.main (sparse D=64 comb, one cursor) under the Byteman agent with bt.btm and prints the helper's stats file.
set -u
T=$1; HJ=$2; CL=$3; JU=$4; OUT=$5; HARN=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT; rm -f $OUT/bt-stats.txt
BM=$T/build/lib/jars/byteman-4.0.20.jar
OPTS=$(grep -v '^#' $T/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
CP="$CL:$T/build/classes/main:$T/build/lib/jars/*"
java $OPTS -javaagent:$T/build/lib/jars/jamm-0.4.0.jar -javaagent:$BM=listener:false,boot:$BM,boot:$HJ,script:$HARN/bt.btm -Dstage4.bt.stats=$OUT/bt-stats.txt -cp "$CP" org.apache.cassandra.db.tries.BacktrackSizeTest > $OUT/main.out 2>&1
echo "exit $?"; grep -a "MAIN_RESULT\|Byteman\|Exception\|rror" $OUT/main.out | head -20; echo "--- stats:"; cat $OUT/bt-stats.txt
