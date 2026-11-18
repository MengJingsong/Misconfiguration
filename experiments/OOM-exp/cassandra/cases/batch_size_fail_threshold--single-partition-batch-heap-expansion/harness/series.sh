#!/usr/bin/env bash
# B14 series: run.sh for each "<rid> <conf> <heap> <arm> <N> <hold>" line of the list file, in order; dump analysis after
# each run that left an .hprof. No run starts after 10:40 America/New_York.
W=/mydata/s4/b14-w3; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
while read -r rid conf heap arm n hold histo; do
  [ -z "$rid" ] && continue
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1040 ]; then echo "$(date +%FT%T) SKIP $rid (ET $now >= 1040)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run.sh $rid $conf $heap $arm $n $hold
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
