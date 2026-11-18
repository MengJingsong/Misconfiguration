#!/usr/bin/env bash
# Resume chain 2 (2026-11-18, amendment A4): after the HS8G fill (seq PID $1) ends, the last heap-search steps:
# HS16Gx = MAX_HEAP_SIZE=15872M set explicitly (the §2.4 arithmetic step), then, if it OOMs, HS31G = MAX_HEAP_SIZE unset
# (cassandra-env with G1 resolves 31744M on pc99; guard 48G >= heap + resolved direct 15872M). Stop at the first survivor;
# then fill the largest failing of these to 3; a surviving step gets 2 more runs if time allows (seq-r.sh: none after 06:30 EST).
set -uo pipefail
R=/mydata/s4/u3-w1; H=$R/harness; FILLPID=$1
while kill -0 "$FILLPID" 2>/dev/null; do sleep 10; done
echo "$(date) chain-r2 start (fill done)" >> $R/chain-r.log
printf 'HS16Gx 15872M 30G s8m set 16\nHS31G unset 48G s8m set 16\n' > $H/spec-hs-r2.txt
bash $H/seq-r.sh $H/spec-hs-r2.txt hs-r2
BEST=""; SURV=""
for s in HS16Gx HS31G; do
  if grep -q '^A2OUTCOME OOM' $R/runs/$s/logs/analysis.txt 2>/dev/null; then BEST=$s
  elif [ -e $R/runs/$s/logs/analysis.txt ]; then SURV=$s; break; fi
done
echo "$(date) chain-r2: largest failing: ${BEST:-none}; first surviving: ${SURV:-none}" >> $R/chain-r.log
for S in $BEST $SURV; do
  : > $H/spec-$S-more.txt
  for n in r2 r3; do grep "^$S " $H/spec-hs-r2.txt | sed "s/^$S /${S}$n /" >> $H/spec-$S-more.txt; done
  bash $H/seq-r.sh $H/spec-$S-more.txt more-$S
done
echo "$(date) chain-r2 done" >> $R/chain-r.log
