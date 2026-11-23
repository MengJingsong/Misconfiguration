#!/usr/bin/env bash
# B22 batch 3 (2026-11-21 10:02 EST): E2 gave a mixed outcome (E2-3 heap OOM, E2-1/2 survived), so the protocol's
# "expand repetitions if timing produces mixed outcomes" applies. Within the design's stopping budget (§2.8: <= 15 readings
# lifetimes, 14 used; <= 5 search/optional lifetimes, 3 used): E2-4, E2-5 (optional budget) and T6-4 (15th readings lifetime,
# same heap condition as E2 with the resolved direct limit). No lifetime starts at or after 13:15 EST.
set -uo pipefail
ROOT=/mydata/s4/b22; H=$ROOT/harness
sed -n '/^REPO=/,/^}/p;/^isoom/p' $H/batch2.sh > /tmp/b22-fns.sh; LAST=$(date -d '2026-11-21 13:15 EST' +%s)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] BATCH3 $*"; }
source /tmp/b22-fns.sh
run E2-4 wide QUORUM 32000 6 2G 1024M
run E2-5 wide QUORUM 32000 6 2G 1024M
run T6-4 wide QUORUM 32000 6 2G auto
log "batch3 done"; tail -3 $ROOT/batch.outcomes
