#!/usr/bin/env bash
# Resume chain (2026-11-18): HS4G already OOM by the A2 rule (first OutOfMemoryError at 38.1 s); continue the heap search at
# 8G then 15872M (stop climbing at the first survivor), then fill the largest failing step to 3 runs; if a step survived and time
# allows, 2 more runs at that boundary step.
set -uo pipefail
R=/mydata/s4/u3-w1; H=$R/harness
echo "$(date) resume chain start" >> $R/chain-r.log
grep -E '^(HS8G|HS16G) ' $H/spec-hs.txt > $H/spec-hs-r.txt
bash $H/seq-r.sh $H/spec-hs-r.txt hs-r
BEST=HS4G; SURV=""
for s in HS8G HS16G; do
  if grep -q '^A2OUTCOME OOM' $R/runs/$s/logs/analysis.txt 2>/dev/null; then BEST=$s
  elif [ -e $R/runs/$s/logs/analysis.txt ]; then SURV=$s; break; fi
done
echo "$(date) largest failing step: $BEST; first surviving step: ${SURV:-none}" >> $R/chain-r.log
: > $H/spec-fill-r.txt
for n in r2 r3; do grep "^$BEST " $H/spec-hs.txt | sed "s/^$BEST /${BEST}$n /" >> $H/spec-fill-r.txt; done
bash $H/seq-r.sh $H/spec-fill-r.txt fill-r
if [ -n "$SURV" ]; then
  : > $H/spec-bound-r.txt
  for n in r2 r3; do grep "^$SURV " $H/spec-hs.txt | sed "s/^$SURV /${SURV}$n /" >> $H/spec-bound-r.txt; done
  bash $H/seq-r.sh $H/spec-bound-r.txt bound-r
fi
echo "$(date) resume chain done" >> $R/chain-r.log
