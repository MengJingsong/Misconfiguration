#!/usr/bin/env bash
# o72 unit tier (B2e with amendments M1-M4, M9). Runs on the node as a non-root user.
# Usage: unit-run.sh   (expects /mydata/jingsong-cass-s4/o72/build-copy built with `ant build-test`,
#                       and DeletingArchiverBoundTest.java next to this script)
# Every command and its output goes to $W/logs/unit-driver.log (set -x + tee).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
BASE=/mydata/jingsong-cass-s4/o72
W=$BASE/unit
mkdir -p $W/logs $W/results
exec > >(tee -a $W/logs/unit-driver.log) 2>&1
set -x
date; date +%s%3N; hostname; uname -m; id -u
[ "$(id -u)" != 0 ] || { echo "must not run as root (A4)"; exit 1; }
[ -d $W/src ] || cp -a $BASE/build-copy $W/src
TD=$W/src/test/unit/org/apache/cassandra/utils/binlog
cp $HERE/DeletingArchiverBoundTest.java $TD/
sha256sum $TD/DeletingArchiverBoundTest.java
export O72_DIR=$W/out
mkdir -p $O72_DIR
cd $W/src
CLS=org.apache.cassandra.utils.binlog.DeletingArchiverBoundTest
OUTXML() { echo "$W/src/build/test/output/TEST-$CLS-$1.xml"; }

run_test() { # $1 tag, $2 method
  local tag=$1 m=$2
  rm -f "$(OUTXML $m)"
  set +e
  ant testsome -Dtest.name=$CLS -Dtest.methods=$m </dev/null > $W/logs/ant-$tag.log 2>&1
  local rc=$?
  set -e
  tail -25 $W/logs/ant-$tag.log
  cp "$(OUTXML $m)" $W/results/TEST-$tag.xml
  python3 $HERE/extract_o72.py $W/logs/ant-$tag.log > $W/results/$tag-readings.txt
  grep -h "Deleted chronicle store file\|Failed to delete chronicle\|rolled file size" $W/logs/ant-$tag.log | grep -v SubstituteLogger > $W/results/$tag-archiverlog.txt || true
  grep "Deleted chronicle store file" $W/results/$tag-archiverlog.txt > $W/results/$tag-deletions.txt || true
  echo "ant rc=$rc for $tag; readings: $(wc -l < $W/results/$tag-readings.txt)"
  [ $rc = 0 ] || { echo "ant failed for $tag"; exit 2; }
}

# --- Test A (+A4)
run_test A synthetic
# collect the DeletingArchiver ERROR/INFO lines from the test logs
grep -rh "Failed to delete chronicle store file" build/test/logs 2>/dev/null > $W/results/A-errorlines.txt || true
wc -l $W/results/A-errorlines.txt
chmod -R u+w $O72_DIR || true
rm -rf $O72_DIR/A-* $O72_DIR/A4-*

run_B() { # $1 tag, $2 limit, $3 seconds
  local tag=$1
  export O72_LIMIT=$2 O72_SECONDS=$3
  ( while sleep 1; do echo "$(date +%s%3N) $(du -B1 -s $O72_DIR/B-* 2>/dev/null | tr '\t\n' '  ')"; done ) > $W/results/du-$tag.txt &
  local dupid=$!
  run_test $tag realBinLog || { kill $dupid; exit 2; }
  kill $dupid; wait $dupid 2>/dev/null || true
  ls -l $O72_DIR/B-*/ > $W/results/ls-$tag.txt 2>&1 || true
  rm -rf $O72_DIR/B-*
  unset O72_LIMIT O72_SECONDS
}

# --- B0 (calibration, positive control; M2: 1 TiB)
run_B B0 1099511627776 40
FP=$(grep '^O72B-LEN' $W/results/B0-readings.txt | sed 's/.*lenAtFirstSeen=\([0-9]*\).*/\1/' | sort -n | awk '{a[NR]=$1} END{ if(NR%2) print a[(NR+1)/2]; else print int((a[NR/2]+a[NR/2+1])/2) }')
echo "F'=$FP"
[ -n "$FP" ] && [ "$FP" -gt 0 ] || { echo "no F' from B0"; exit 3; }
SECS=40; [ "$FP" -le $((30*1024*1024)) ] || SECS=120
echo "Fprime=$FP seconds=$SECS B1=$((FP*5/2)) B2=$((FP*11/2))" | tee $W/results/fprime.txt
run_B B1 $((FP*5/2)) $SECS
run_B B2 $((FP*11/2)) $SECS
rm -rf $O72_DIR
pgrep -u $(id -u) -f DeletingArchiverBoundTest -a || echo "no test JVM left"
date; echo UNIT-DONE
