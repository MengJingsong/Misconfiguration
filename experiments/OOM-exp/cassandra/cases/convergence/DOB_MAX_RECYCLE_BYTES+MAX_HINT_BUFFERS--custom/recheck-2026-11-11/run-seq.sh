#!/usr/bin/env bash
# R2 recheck runner: runs the arms given as "name|args" lines in sequence, with the pinned filed condition.
# Usage: run-seq.sh <listfile>
cd /mydata/oom-recheck/R2
export N_HINTS=${N_HINTS:-6000000} N_DOB=${N_DOB:-1500} HINT_LEAD=${HINT_LEAD:-20}
echo "[$(date '+%F %T')] run-seq start: N_HINTS=$N_HINTS N_DOB=$N_DOB HINT_LEAD=$HINT_LEAD list=$1"
while IFS= read -r line; do
  [ -z "$line" ] && continue; case "$line" in \#*) continue;; esac
  echo "[$(date '+%F %T')] === arm $line"
  bash ./oom-run.sh arm $line > /dev/null 2>&1; rc=$?
  echo "[$(date '+%F %T')] === arm $line rc=$rc; daemons left: $(pgrep -fc '[o]rg.apache.cassandra.service.CassandraDaemon'); stress left: $(pgrep -fc '[o]rg.apache.cassandra.stress.Stress')"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null; pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  sleep 5
done < "$1"
echo "[$(date '+%F %T')] run-seq DONE"
