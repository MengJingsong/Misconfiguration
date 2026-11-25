#!/bin/bash
# B2 unit tier (as amended S4-A1). Runs on the node. Logs every command and its output.
set -u
RUN=/mydata/jingsong-cass-s4/o119
LOG=$RUN/probe/unit-session.txt
mkdir -p $RUN/probe/src/org/apache/cassandra/io/util $RUN/probe/classes
cp $RUN/harness/DobGrowthProbe.java $RUN/probe/src/org/apache/cassandra/io/util/DobGrowthProbe.java
exec > >(tee -a $LOG) 2>&1
x() { echo "+ [$(date -u +%FT%T.%3NZ)] $*"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
x java -version
x df -h $RUN
x free -g
cd $RUN/probe
x javac -cp "$RUN/cassandra/build/classes/main:$RUN/cassandra/lib/*:$RUN/cassandra/build/lib/jars/*" -d classes src/org/apache/cassandra/io/util/DobGrowthProbe.java || exit 1
JOPTS=$(grep -v "^#" $RUN/cassandra/conf/jvm11-clients.options | grep -v "^[[:space:]]*$" | tr "\n" " ")   # S4-D1
echo "JOPTS=$JOPTS"
CP="$RUN/probe/classes:$RUN/cassandra/build/classes/main:$RUN/cassandra/lib/*:$RUN/cassandra/build/lib/jars/*:$RUN/cassandra/conf"
run() { # out-file then java args
  local out=$1; shift
  echo "+ [$(date -u +%FT%T.%3NZ)] java \$JOPTS $* > $out"
  java $JOPTS "$@" > $out 2> ${out%.txt}.err; local rc=$?
  echo "  rc=$rc; $(grep -h 'DOUBLING\|FINAL\|OVERFLOW' $out | tr '\n' ' ')"
  [ -s ${out%.txt}.err ] && { echo "  stderr:"; head -5 ${out%.txt}.err; }
  return $rc
}
# step 3: default (unset)
run out-unset-bytes200.txt -Xms2g -Xmx2g -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe bytes 200 || exit 1
run out-unset-rows200.txt -Xms2g -Xmx2g -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe rows 200 || exit 1
# step 4
for T in 0 16 64 128 1024; do
  for mn in "bytes 200" "bytes 100" "rows 200" "rows 100"; do
    set -- $mn
    run out-T$T-$1$2.txt -Xms2g -Xmx2g -Dcassandra.DOB_DOUBLING_THRESHOLD_MB=$T -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe $1 $2 || exit 1
  done
done
# step 5: positive control
run out-fixed.txt -Xms2g -Xmx2g -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe fixed 200 || exit 1
# step 6: repeat bytes 200 per T
mkdir -p repeat
for T in 0 16 64 128 1024; do
  run repeat/out-T$T-bytes200.txt -Xms2g -Xmx2g -Dcassandra.DOB_DOUBLING_THRESHOLD_MB=$T -cp "$CP" org.apache.cassandra.io.util.DobGrowthProbe bytes 200 || exit 1
  if cmp -s <(grep -h 'DOUBLING\|EXPAND\|FINAL' out-T$T-bytes200.txt) <(grep -h 'DOUBLING\|EXPAND\|FINAL' repeat/out-T$T-bytes200.txt); then echo "  REPEAT T=$T identical"; else echo "  REPEAT T=$T DIFFERS"; fi
done
echo "+ summary"; grep -H "DOUBLING\|FINAL\|OVERFLOW" out-*.txt
echo UNIT-DONE
