#!/usr/bin/env bash
# Driver for run 1 of MAX_KEY_SIZE-write-limit-2--autonomous (attempt 2, node pc91). Runs ON THE NODE, detached.
# Usage: driver.sh <run-dir>     (<run-dir>/harness holds the harness; <run-dir>/src must not exist yet)
# Steps, stopping at the first failure: copy the source (copy-source.sh), instrument check (unit-run.sh --compile-only),
# unit tier (unit-run.sh), cluster tier (cluster-run.sh). Each step logs under <run-dir>/logs/; this script's own
# log is <run-dir>/logs/driver.log. Removes its PID file /mydata/s4/DRIVER-jingsong-h6.pid on exit.
set -uo pipefail
RUN=${1:?usage: driver.sh <run-dir>}
PIDF=/mydata/s4/DRIVER-jingsong-h6.pid
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
mkdir -p "$RUN/logs"
exec >> "$RUN/logs/driver.log" 2>&1
trap 'echo "DRIVER EXIT rc=$? $(date "+%F %T")"; rm -f "$PIDF"' EXIT
echo "DRIVER START $(date '+%F %T') pid $$ host $(hostname)"
run(){ echo "+ [$(date '+%F %T')] $*"; "$@"; local rc=$?; echo "  rc=$rc [$(date '+%F %T')]"; return $rc; }
run git -C "$REPO" status --short systems/hadoop/source || exit 11
run "$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh" "$RUN/src" || exit 12
run bash "$RUN/harness/unit-run.sh" "$RUN" --compile-only || exit 13
run bash "$RUN/harness/unit-run.sh" "$RUN" || exit 14
run bash "$RUN/harness/cluster-run.sh" "$RUN" || exit 15
echo "DRIVER ALL STEPS DONE $(date '+%F %T')"
