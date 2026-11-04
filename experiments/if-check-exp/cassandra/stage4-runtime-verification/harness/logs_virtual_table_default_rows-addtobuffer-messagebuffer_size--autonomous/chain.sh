#!/usr/bin/env bash
# Run 1 of logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous, one background job on one node (pc39): unit tier, then the cluster runs of B3e.
# Precondition: ~/s4-lv (build A, ant build-test), ~/s4-lvB (build B), seed in ~/stage4-tmp/lv/seed (seed-run.sh). Logs: ~/stage4-logs/lv/run1/.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); L=$HOME/stage4-logs/lv/run1; mkdir -p $L; export OUT=$L/cluster
exec > >(tee -a $L/chain.log) 2>&1
echo "== chain start $(date -u +%FT%TZ) on $(hostname)"; ps -eo cmd | grep '[C]assandraDaemon' && { echo "daemon running, abort"; exit 1; }
echo "-- unit tier"; $H/unit-run.sh $HOME/s4-lv $L/unit
echo "-- cluster tier"
run() { echo "== run $* $(date -u +%FT%TZ)"; python3 $H/cluster-run.py "$@" || echo "RUN FAILED rc=$?"; ps -eo cmd | grep '[C]assandraDaemon' && { echo "daemon left after $1"; pkill -f CassandraDaemon; sleep 5; }; }
run R1-A-off       A off 100000 full
run R2-A-on-100k   A on  100000 full
run R3-B-on-100k   B on  100000 full
run R4-A-on-1000   A on  1000   full
run R2r2-A-on-100k A on  100000 startup
run R2r3-A-on-100k A on  100000 startup
run R3r2-B-on-100k B on  100000 startup
run R3r3-B-on-100k B on  100000 startup
echo "== chain end $(date -u +%FT%TZ)"; ps -eo cmd | grep '[C]assandraDaemon' || echo "no daemon left"
