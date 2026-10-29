#!/usr/bin/env bash
# Run 1 of max_shard_split-getnumshards-count--autonomous on pc39: unit tier (ant testsome), then the cluster tier (one node start, all phases).
# Precondition: ~/s4-ms (copy-source.sh copy, ant build-test). Logs: ~/stage4-logs/ms/run1/.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); L=$HOME/stage4-logs/ms/run1; mkdir -p $L; export OUT=$L/cluster
exec > >(tee -a $L/chain.log) 2>&1
echo "== chain start $(date -u +%FT%TZ) on $(hostname)"; ps -eo cmd | grep '[C]assandraDaemon' && { echo "daemon running, abort"; exit 1; }
echo "-- unit tier"; $H/unit-run.sh $HOME/s4-ms $L/unit
echo "-- cluster tier"; python3 $H/cluster-run.py run1 || echo "RUN FAILED rc=$?"
ps -eo cmd | grep '[C]assandraDaemon' && { echo "daemon left"; pkill -f CassandraDaemon; }
echo "== chain end $(date -u +%FT%TZ)"; ps -eo cmd | grep '[C]assandraDaemon' || echo "no daemon left"
