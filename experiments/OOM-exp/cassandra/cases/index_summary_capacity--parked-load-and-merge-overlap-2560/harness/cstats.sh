#!/usr/bin/env bash
# R18 copy of R10's cstats.sh (unchanged): <nodetool> <jmx port> <pid> <out> : `nodetool compactionstats` every 5 s while <pid> lives (one line per
# task: epoch_ms|compaction line), pinned to odd CPUs (off the victim's).
nt=$1; jp=$2; pid=$3; out=$4
while kill -0 $pid 2>/dev/null; do
  t=$(date +%s%3N)
  r=$(timeout 20 taskset -c 17,19,21,23,25,27,29,31 $nt -p $jp compactionstats 2>&1 | grep -E 'isx|pending tasks' | tr -s ' ' | tr '\n' ';')
  echo "$t|$r" >> $out
  sleep 5
done
