#!/usr/bin/env bash
# Runs the cluster labels of concurrent_compactors in the order of case 9e (A default, B 1/4/8, C control), then the two default repeats (noise band, 9f R4).
cd ~
for l in "$@"; do
  echo "$(date +%T) start $l"
  ~/stage4-harness-run/cc/cluster-run.py run $l > ~/stage4-logs/cc/$l.out 2>&1 || { echo "$(date +%T) FAILED $l"; exit 1; }
  echo "$(date +%T) done $l"
done
