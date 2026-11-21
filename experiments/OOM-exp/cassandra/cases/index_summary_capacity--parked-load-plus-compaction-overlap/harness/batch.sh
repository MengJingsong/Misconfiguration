#!/usr/bin/env bash
# R10 batch runner: batch.sh <name> "<arm> <heap> <L> <P> <Q> <red> [role]" ... ; arms run sequentially (one measured
# experiment at a time); log in /mydata/s4/r10/logs/batch-<name>.log. A file /mydata/s4/r10/STOP stops before the next arm;
# no arm starts at or after 16:30 America/New_York (design §2.7 stopping budget).
R=/mydata/s4/r10; N=$1; shift; LOG=$R/logs/batch-$N.log
for spec in "$@"; do
  [ -e $R/STOP ] && { echo "$(date '+%F %T') STOP file present; not starting: $spec" >> $LOG; break; }
  hm=$(TZ=America/New_York date +%H%M); [ $hm -ge 1630 ] && { echo "$(date '+%F %T') past 16:30 EST; not starting: $spec" >> $LOG; break; }
  echo "$(date '+%F %T') START $spec" >> $LOG
  bash $R/gen/arm.sh $spec > /dev/null 2>&1; rc=$?
  echo "$(date '+%F %T') END rc=$rc $spec :: $(python3 $R/gen/analyze.py $R/arms/$(echo $spec | cut -d' ' -f1) 2>&1 | cut -c1-900)" >> $LOG
  sleep 5
done
echo "$(date '+%F %T') BATCH DONE" >> $LOG
