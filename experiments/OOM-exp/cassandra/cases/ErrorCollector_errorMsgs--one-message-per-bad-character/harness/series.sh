#!/usr/bin/env bash
# U6 series: run.sh for each "<rid> <build> <heap> <payload> <N> <hold> [histo|-] [len]" line of the list file, in order;
# dump analysis after each run that left an .hprof (then the .hprof is deleted). No run starts at/after 17:20 America/New_York.
W=/mydata/s4/u6-w4; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
while read -r rid build heap arm n hold histo len; do
  [ -z "$rid" ] && continue
  case $rid in \#*) continue;; esac
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1720 ]; then echo "$(date +%FT%T) SKIP $rid (ET $now >= 1720)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run.sh $rid $build $heap $arm $n $hold $len
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt; sha256sum $f | cut -c1-16 >> $R/dump.txt
    timeout 600 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1
    if [ "$histo" = histo ]; then timeout 900 python3 -I $H/hprof-histo.py $f --top 30 > $R/histo.txt 2>&1; echo "histo rc=$?" >> $R/dump.txt; fi
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
