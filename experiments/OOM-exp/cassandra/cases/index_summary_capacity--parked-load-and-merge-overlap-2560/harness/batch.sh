#!/usr/bin/env bash
# R18 batch runner: batch.sh <name> <queue file>. Runs the arm specs of the queue file in order, one at a time ("<arm> <heap>
# <L> <P> <Q> <red> <alter>", optional "NOQ_END=<s>" first word); lines may be appended while it runs (a repeat of an invalid
# arm). Log /mydata/s4/r18/logs/batch-<name>.log. A file /mydata/s4/r18/STOP stops before the next arm; no arm starts at or
# after 06:45 America/New_York (design §2.7 stopping budget).
R=/mydata/s4/r18; N=$1; Q=$2; LOG=$R/logs/batch-$N.log; i=0
while true; do
  i=$((i+1)); spec=$(sed -n "${i}p" $Q); [ -z "$spec" ] && break
  [ -e $R/STOP ] && { echo "$(date '+%F %T') STOP file present; not starting: $spec" >> $LOG; break; }
  hm=$(TZ=America/New_York date +%H%M); [ $((10#$hm)) -ge 645 ] && [ $((10#$hm)) -lt 1200 ] && { echo "$(date '+%F %T') at/after 06:45 EST; not starting: $spec" >> $LOG; break; }
  env=""; case $spec in NOQ_END=*) env=${spec%% *}; spec=${spec#* };; esac
  echo "$(date '+%F %T') (EST $(TZ=America/New_York date +%T)) START $env $spec" >> $LOG
  env $env bash $R/gen/arm.sh $spec > /dev/null 2>&1; rc=$?
  echo "$(date '+%F %T') (EST $(TZ=America/New_York date +%T)) END rc=$rc $spec :: $(python3 $R/gen/table.py $R/arms/$(echo $spec | cut -d' ' -f1) 2>&1 | cut -c1-1500)" >> $LOG
  sleep 5
done
echo "$(date '+%F %T') BATCH DONE" >> $LOG
