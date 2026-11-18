#!/usr/bin/env bash
# B12 series: runs the arms listed in a spec file sequentially (one measured run at a time).
# Spec line: <run-id> <base|iv> <heap> <K> <SERIAL|ONE> <N_max> <M> <need-GiB> [cap0]
# Stops before a run whose start would be later than the epoch in $W/no-new-run-after (if present).
W=/mydata/s4/b12-w2; SPEC=$1
while read -r rid b h k cl nmax m need cap; do
  [ -z "$rid" ] && continue; case $rid in \#*) continue;; esac
  if [ -f $W/no-new-run-after ] && [ $(date +%s) -gt $(cat $W/no-new-run-after) ]; then echo "$(date +%FT%T) skip $rid (time)" >> $W/series.log; continue; fi
  [ -f $W/stop-series ] && { echo "$(date +%FT%T) stop-series before $rid" >> $W/series.log; break; }
  for i in $(seq 1 60); do ps -eo cmd | grep -q '[C]assandraDaemon' || break; sleep 2; done
  echo "$(date +%FT%T) start $rid" >> $W/series.log
  NEED_G=$need $W/harness/run.sh $rid $b $h $k $cl $nmax $m $cap
  echo "$(date +%FT%T) end $rid: $(grep -m1 '^endpoint' $W/runs/$rid/summary.txt)" >> $W/series.log
done < $SPEC
echo "$(date +%FT%T) series $SPEC finished" >> $W/series.log
