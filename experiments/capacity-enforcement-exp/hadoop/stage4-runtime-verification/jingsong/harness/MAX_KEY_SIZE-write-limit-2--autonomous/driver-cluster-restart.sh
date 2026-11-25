#!/usr/bin/env bash
# Restart of the cluster tier after runbook defect 1 (A11), run 1 of MAX_KEY_SIZE-write-limit-2--autonomous, node pc91.
# Runs ON THE NODE, detached. Usage: driver-cluster-restart.sh <run-dir>
# The previous cluster attempt's logs were moved to <run-dir>/logs/attempt0-runbook-defect/ and its state removed.
set -uo pipefail
RUN=${1:?usage: driver-cluster-restart.sh <run-dir>}
PIDF=/mydata/s4/DRIVER-jingsong-h6.pid
exec >> "$RUN/logs/driver.log" 2>&1
trap 'echo "DRIVER2 EXIT rc=$? $(date "+%F %T")"; rm -f "$PIDF"' EXIT
echo "$$" > "$PIDF"
echo "DRIVER2 START (cluster tier restart after A11) $(date '+%F %T') pid $$"
md5sum "$RUN/harness/cluster-run.sh"
bash "$RUN/harness/cluster-run.sh" "$RUN"
echo "cluster-run rc=$? $(date '+%F %T')"
