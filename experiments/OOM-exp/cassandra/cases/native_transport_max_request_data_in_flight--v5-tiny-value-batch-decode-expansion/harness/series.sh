#!/usr/bin/env bash
# R13 series (from B14's): run.sh for each "<rid> <conf> <heap> <arm> <N> <hold> <histo|-> [last-delay] [nodump]" line of
# the list file, in order; dump analysis after each run that left an .hprof (OOME thread always; class histogram if
# "histo"), then the dump is deleted (at most one .hprof on disk). No run starts at or after 16:30 America/New_York.
W=/mydata/s4/r13-w1; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
while read -r rid conf heap arm n hold histo ld nd; do
  [ -z "$rid" ] && continue
  case "$rid" in \#*) continue;; esac
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1630 ]; then echo "$(date +%FT%T) SKIP $rid (ET $now >= 1630)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run.sh $rid $conf $heap $arm $n $hold ${ld:-0} ${nd:-}
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt; sha256sum $f >> $R/dump.txt
    timeout 600 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1
    vl=1; [ "$arm" = Cp ] && vl=246599
    if [ "$histo" = histo ]; then timeout 1500 python3 -I $H/hprof-histo.py $f --top 30 --value-len $vl > $R/histo.txt 2>&1; fi
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
