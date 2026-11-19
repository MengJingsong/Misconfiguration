#!/usr/bin/env bash
# U8 amendment 2026-11-18 14:55 EST: B steps re-run with the frozen client rule (a client-side timeout does not end the
# run; R=3 rounds or node death or the 600 s budget). Largest heap first: 16 GiB (N=21); if it OOMs, 2 repeats there.
# Otherwise 8 GiB (N=11); if it OOMs, 2 repeats there; otherwise one step between the surviving 8 GiB and the
# last failing 4 GiB per the design dial: 6 GiB with N = ceil(1.25*6)+1 = 9, and 2 repeats if it OOMs.
# No new lifetime after 17:35 EST (batch.sh run()).
set -uo pipefail
ROOT=/mydata/s4/u8-w4; H=$ROOT/harness
source <(sed -n '/^LAST=/p;/^log()/p;/^run()/,/^}/p;/^isoom()/p' $H/batch.sh)
if run B-16G-N21-2 A 16G json 21 3 && isoom B-16G-N21-2; then for k in 3 4; do run B-16G-N21-$k A 16G json 21 3; done
elif run B-8G-N11-2 A 8G json 11 3 && isoom B-8G-N11-2; then for k in 3 4; do run B-8G-N11-$k A 8G json 11 3; done
else run B-6G-N9-1 A 6G json 9 3; if isoom B-6G-N9-1; then for k in 2 3; do run B-6G-N9-$k A 6G json 9 3; done; fi
fi
log "batch-b2 done"; cat $ROOT/batch.outcomes
