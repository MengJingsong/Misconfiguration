#!/bin/bash
# Unit tier (B2e as amended by B2i), plus the instrument check K0 (known answer) first.
# usage: unit-run.sh [check|run]
set -u
. /mydata/jingsong-cass-s4/o115/harness/common.sh
mkdir -p $OUTD
MODE=${1:-run}
exec > >(tee -a $OUTD/unit-driver-$MODE.log) 2>&1
echo "=== unit-run.sh $MODE start $(date -Is) epoch_ms=$(date +%s%3N) host=$(hostname) arch=$(uname -m)"
java -version 2>&1; df -h $S4 | tail -1; free -g | head -2
no_strays || exit 1

set -x
cd $S4/harness && rm -rf classes && mkdir classes && \
  javac -cp "$SRC/build/classes/main:$SRC/build/lib/jars/*:$SRC/lib/*" -d classes org/apache/cassandra/io/sstable/BufferCapProbe.java || { echo "COMPILE FAILED"; exit 1; }
set +x

one() { # one <name> <Xmx> <mode> <rows> <valueBytes>
  local R=$1 X=$2 M=$3 N=$4 V=$5
  local OUT=$OUTD/unit-$R/probe/t
  rm -rf $OUTD/unit-$R; mkdir -p $OUT
  echo "--- $R start $(date -Is) mode=$M rows=$N value=$V Xmx=$X"
  set -x
  probe_unit $X $OUT $M $N $V true 0 2>&1 | tee $OUTD/unit-$R.log
  local rc=${PIPESTATUS[0]}
  set +x
  echo "EXIT $rc" | tee -a $OUTD/unit-$R.log
  ls -l $OUT/*-Data.db 2>&1 | tee -a $OUTD/unit-$R.log
  stat -c '%s %n' $OUT/*-Data.db >> $OUTD/unit-$R.log 2>&1
  echo "DATA_DB_COUNT $(ls $OUT/*-Data.db 2>/dev/null | wc -l)" | tee -a $OUTD/unit-$R.log
  du -sb $OUT >> $OUTD/unit-$R.log
  rm -rf $OUTD/unit-$R
  echo "--- $R end $(date -Is) rc=$rc"
  return $rc
}

if [ "$MODE" = check ]; then
  # K0: explicit:1 MiB, 3000 x 60000 B rows. n = floor(1048576/(60000+d))+1 = 18 for d in [0,100]
  # -> 3000/18 = 166 syncs (166*18=2988), 12 rows left -> 167 Data.db, LIMIT_BYTES 1048576.
  one K0 1g explicit:1 3000 60000 || { echo "K0 FAILED"; exit 1; }
else
  one U1 1g default 18000 60000      || { echo "U1 failed"; exit 1; }
  one U2 1g explicit:0 18000 60000   || { echo "U2 failed"; exit 1; }
  one U3 1g explicit:32 18000 60000  || { echo "U3 failed"; exit 1; }
  one U4 3g explicit:2047 18000 60000 || { echo "U4 failed"; exit 1; }
  one U5 1g sorted 0 60000           || { echo "U5 failed"; exit 1; }
fi
no_strays
echo "=== unit-run.sh $MODE end $(date -Is)"
