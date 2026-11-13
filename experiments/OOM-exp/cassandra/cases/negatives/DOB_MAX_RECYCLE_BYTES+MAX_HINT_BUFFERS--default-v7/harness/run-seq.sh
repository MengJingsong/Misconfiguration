#!/usr/bin/env bash
# R6-V runner: each non-comment line of the list is "<name> <budget_MiB> [VAR=value ...]"; arms run in sequence.
# Usage: run-seq.sh <listfile>   (progress in /mydata/r6v/run-seq.log)
cd /mydata/r6v; LIST=$1
echo "[$(date '+%F %T')] run-seq start list=$1" >> run-seq.log
while IFS= read -r line; do
  [ -z "$line" ] && continue; case "$line" in \#*) continue;; esac
  set -- $line; name=$1; budget=$2; shift 2
  if [ -f "logs/$name/session.log" ] && grep -q "ARM $name DONE" "logs/$name/session.log"; then echo "[$(date '+%F %T')] skip $name (done)" >> run-seq.log; continue; fi
  echo "[$(date '+%F %T')] === arm $name $budget $*" >> run-seq.log
  env "$@" bash ./oom-run.sh arm "$name" "$budget" > /dev/null 2>&1; rc=$?
  echo "[$(date '+%F %T')] === arm $name rc=$rc; daemons left: $(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon'); stress left: $(pgrep -fc '[o]rg.apache.cassandra.stress.Stress'); $(grep -E 'PEAK|N1 alive' logs/$name/summary.txt 2>/dev/null | tr '\n' ' ')" >> run-seq.log
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null; pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  sleep 5
done < "$LIST"
echo "[$(date '+%F %T')] run-seq DONE $LIST" >> run-seq.log
