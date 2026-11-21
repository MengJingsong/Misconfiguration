#!/usr/bin/env bash
# R15 series (from U6's): run.sh for each "<rid> <build> <heap> <payload> <N> <k> <trig-spec> <hold> <histo|-> [len|-] [tmax]"
# line of the list file, in order; dump analysis after each run that left an .hprof (OOME thread always; histogram if
# 'histo'; each capped at 15 min), then the .hprof is deleted. No run starts at/after 16:40 America/New_York.
# A line "SKIPIF-SURVIVED <rid>" (or "SKIPIF-OOM <rid>") skips the following lines up to the next "ENDSKIP" when <rid> ended without an OOM (with an OOM).
W=/mydata/s4/r15-w5; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
skip=""
while read -r rid build heap arm n k tspec hold histo len tmax; do
  [ -z "$rid" ] && continue
  case $rid in \#*) continue;; esac
  if [ "$rid" = SKIPIF-SURVIVED ]; then
    if ! grep -q "oom:" $W/runs/$build/driver.txt 2>/dev/null; then skip=1; echo "$(date +%FT%T) skip rule: $build survived" >> $LOG; fi
    continue
  fi
  if [ "$rid" = SKIPIF-OOM ]; then
    if grep -q "oom:" $W/runs/$build/driver.txt 2>/dev/null; then skip=1; echo "$(date +%FT%T) skip rule: $build ended in OOM" >> $LOG; fi
    continue
  fi
  [ "$rid" = ENDSKIP ] && { skip=""; continue; }
  [ -n "$skip" ] && { echo "$(date +%FT%T) SKIP $rid (skip rule)" >> $LOG; continue; }
  [ -e $W/runs/HALT ] && { echo "$(date +%FT%T) SKIP $rid (HALT file)" >> $LOG; continue; }
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 1640 ]; then echo "$(date +%FT%T) SKIP $rid (ET $now >= 1640)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run.sh $rid $build $heap $arm $n $k $tspec $hold ${len:--} ${tmax:-300}
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt; sha256sum $f | cut -c1-16 >> $R/dump.txt
    timeout 900 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1; echo "oome-thread rc=$?" >> $R/dump.txt
    if [ "$histo" = histo ]; then timeout 900 python3 -I $H/hprof-histo.py $f --len-range 47 54 --top 30 > $R/histo.txt 2>&1; echo "histo rc=$?" >> $R/dump.txt; fi
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
