#!/usr/bin/env bash
# R13 3-b confirm series (2026-11-23, from stage 2's series.sh): run3b.sh for each "<rid> <mode> <N> <hold> <histo|-> [ips]"
# line of the list file, in order; after a run that left an .hprof: OOME thread always, class histogram if "histo", then the
# dump is deleted (at most one .hprof on disk). Wall-clock cap: no run starts after DEADLINE (epoch s, env, default +4 h).
W=/mydata/s4/3b-R13; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
DEADLINE=${DEADLINE:-$(( $(date +%s) + 14400 ))}
while read -r rid mode n hold histo ips; do
  [ -z "$rid" ] && continue
  case "$rid" in \#*) continue;; esac
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then echo "$(date +%FT%T) SKIP $rid (deadline)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run3b.sh $rid $mode $n $hold ${ips:-0}
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt; sha256sum $f >> $R/dump.txt
    timeout 600 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1
    if [ "$histo" = histo ]; then timeout 1500 python3 -I $H/hprof-histo.py $f --top 30 --value-len 1 > $R/histo.txt 2>&1; fi
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
