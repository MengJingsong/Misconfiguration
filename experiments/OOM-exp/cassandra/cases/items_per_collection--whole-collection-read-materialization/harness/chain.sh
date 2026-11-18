#!/usr/bin/env bash
# After the main batch (PID $1) ends: heap search (S8, stop climbing at the first survivor), then 2 more runs at the
# largest failing step (fill to 3), then the optional diagnostic arm P x3 (S9). seq.sh enforces the 02:05 EST no-new-run rule.
set -uo pipefail
R=/mydata/s4/u3-w1; H=$R/harness; MAINPID=$1
while kill -0 "$MAINPID" 2>/dev/null; do sleep 10; done
echo "$(date) main done; heap search" >> $R/chain.log
bash $H/seq.sh $H/spec-hs.txt hs
BEST=""
for s in HS4G HS8G HS16G; do grep -q '^OUTCOME OOM' $R/runs/$s/logs/analysis.txt 2>/dev/null && BEST=$s; done
echo "$(date) largest failing step: ${BEST:-none}" >> $R/chain.log
if [ -n "$BEST" ]; then
  grep "^$BEST " $H/spec-hs.txt | sed "s/^$BEST /${BEST}r2 /" > $H/spec-fill.txt
  grep "^$BEST " $H/spec-hs.txt | sed "s/^$BEST /${BEST}r3 /" >> $H/spec-fill.txt
  bash $H/seq.sh $H/spec-fill.txt fill
fi
printf 'P1 2G 16G s1m set 16 %s\nP2 2G 16G s1m set 16 %s\nP3 2G 16G s1m set 16 %s\n' $H/arm-P.yaml $H/arm-P.yaml $H/arm-P.yaml > $H/spec-P.txt
bash $H/seq.sh $H/spec-P.txt P
echo "$(date) chain done" >> $R/chain.log
