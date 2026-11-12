#!/usr/bin/env bash
# R3 batch runner: runs oom-run.sh invocations sequentially (one per line of the batch file), with
# hygiene checks between arms. Usage: run-batch.sh <batchfile>; lines: "<env assignments> -- <oom-run.sh args>"
R=/mydata/oom-recheck/R3
B=$1
echo "[$(date '+%F %T')] batch $B start on $(hostname)"
while IFS= read -r line; do
  [ -z "$line" ] && continue; case "$line" in \#*) continue;; esac
  envs=${line%%--*}; args=${line#*--}
  echo "[$(date '+%F %T')] ARM START: env[$envs] args[$args]"
  env $envs bash $R/harness/oom-run.sh $args > /dev/null 2>&1; rc=$?
  echo "[$(date '+%F %T')] ARM END rc=$rc: $args"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null
  if pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; then
    echo "WARNING: CassandraDaemon still running after arm; killing"; pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'; sleep 2; fi
  sleep 5
done < "$B"
echo "[$(date '+%F %T')] batch $B done; daemons: $(pgrep -fc '[C]assandraDaemon'); stress: $(pgrep -fc '[o]rg.apache.cassandra.stress.Stress')"
