#!/usr/bin/env bash
# C4 batch runner: batch.sh <name> "<arm> <heap> <L> <sets> [src]" ... ; runs arms sequentially, logs to /mydata/s4/c4-w1/logs/batch-<name>.log
R=/mydata/s4/c4-w1; N=$1; shift; LOG=$R/logs/batch-$N.log
for spec in "$@"; do
  echo "$(date '+%F %T') START $spec" >> $LOG
  $R/gen/arm.sh $spec > /dev/null 2>&1; echo "$(date '+%F %T') END rc=$? $spec :: $(python3 $R/gen/analyze.py $R/arms/$(echo $spec | cut -d' ' -f1) 2>&1)" >> $LOG
  sleep 5
done
echo "$(date '+%F %T') BATCH DONE" >> $LOG
