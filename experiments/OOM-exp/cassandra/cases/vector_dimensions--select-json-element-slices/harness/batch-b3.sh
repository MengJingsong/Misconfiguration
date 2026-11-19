#!/usr/bin/env bash
# U8 amendment 2026-11-18 15:10 EST: B steps observed to the frozen 600 s per-run budget even when the client gives up
# (run-arm.sh watch rule). Largest heap first: 16 GiB (N=21); if it OOMs, 2 repeats there. Otherwise 8 GiB (N=11);
# if it OOMs, 2 repeats; otherwise 6 GiB (N=9, the step between the surviving 8 GiB and the failing 4 GiB) and 2
# repeats if it OOMs. No new lifetime after 17:35 EST (batch.sh run()).
set -uo pipefail
ROOT=/mydata/s4/u8-w4; H=$ROOT/harness
source <(sed -n '/^LAST=/p;/^log()/p;/^run()/,/^}/p;/^isoom()/p' $H/batch.sh)
if run B-16G-N21-w1 A 16G json 21 3 && isoom B-16G-N21-w1; then for k in 2 3; do run B-16G-N21-w$k A 16G json 21 3; done
elif run B-8G-N11-w1 A 8G json 11 3 && isoom B-8G-N11-w1; then for k in 2 3; do run B-8G-N11-w$k A 8G json 11 3; done
else run B-6G-N9-w1 A 6G json 9 3; if isoom B-6G-N9-w1; then for k in 2 3; do run B-6G-N9-w$k A 6G json 9 3; done; fi
fi
log "batch-b3 done"; cat $ROOT/batch.outcomes
