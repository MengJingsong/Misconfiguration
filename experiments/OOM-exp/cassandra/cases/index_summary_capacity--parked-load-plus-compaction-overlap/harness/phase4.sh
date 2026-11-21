#!/usr/bin/env bash
# R10 phase 4 (design §2.5): after phase 3's batch is done, U1 = T at heap 1,280 / L 2,560; only if U1 is killed, U2 = T at
# 1,536 / 3,072. batch.sh keeps the 16:30 EST no-start rule.
R=/mydata/s4/r10
while ! grep -q "BATCH DONE" $R/logs/batch-phase3.log; do sleep 10; done
bash $R/gen/batch.sh phase4 "U1 1280 2560 1 1 0"
if grep -q "U1.*oom_kill=1" $R/logs/batch-phase4.log; then bash $R/gen/batch.sh phase4b "U2 1536 3072 1 1 0"; fi
echo "$(date '+%F %T') PHASE4 DONE" >> $R/logs/batch-phase4.log
