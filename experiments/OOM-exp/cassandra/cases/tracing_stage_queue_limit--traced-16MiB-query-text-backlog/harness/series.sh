#!/usr/bin/env bash
# B28 series (stage 2, 2026-11-24; from R15's series.sh): run.sh for each "<rid> <build> <heap> <traced|untraced> <spec> <hold>"
# line of the list file, in order. After each run that left an .hprof: OOME-initiating thread (hprof_oome_thread.py) and
# owner totals (owners.py), each capped at 25 min, then the .hprof is deleted unless the run id is listed in $W/KEEP-DUMPS.
# "SKIPIF-SURVIVED <rid>" / "SKIPIF-OOM <rid>" skip the following lines up to "ENDSKIP". A $W/runs/HALT file stops the series.
# No run starts at or after $CUTOFF (HHMM America/Denver; default 2215 for the pc82 re-run of 2026-11-24, wall-clock cap 23:10).
W=/mydata/s4/b28; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
skip=""
while read -r rid build heap tr spec hold; do
  [ -z "$rid" ] && continue
  case $rid in \#*) continue;; esac
  if [ "$rid" = SKIPIF-SURVIVED ]; then
    grep -q "oom:" $W/runs/$build/driver.txt 2>/dev/null || { skip=1; echo "$(date +%FT%T) skip rule: $build survived" >> $LOG; }
    continue
  fi
  if [ "$rid" = SKIPIF-OOM ]; then
    grep -q "oom:" $W/runs/$build/driver.txt 2>/dev/null && { skip=1; echo "$(date +%FT%T) skip rule: $build ended in OOM" >> $LOG; }
    continue
  fi
  [ "$rid" = ENDSKIP ] && { skip=""; continue; }
  [ -n "$skip" ] && { echo "$(date +%FT%T) SKIP $rid (skip rule)" >> $LOG; continue; }
  [ -e $W/runs/HALT ] && { echo "$(date +%FT%T) SKIP $rid (HALT file)" >> $LOG; continue; }
  now=$(TZ=America/Denver date +%H%M)
  if [ "$now" -ge "${CUTOFF:-2215}" ]; then echo "$(date +%FT%T) SKIP $rid (MT $now >= ${CUTOFF:-2215})" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  bash $H/run.sh $rid $build $heap $tr $spec $hold
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt
    timeout 1500 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1; echo "oome-thread rc=$?" >> $R/dump.txt
    /usr/bin/time -v timeout 1500 python3 -I $H/owners.py $f > $R/owners.txt 2> $R/owners.err; echo "owners rc=$? $(grep -E 'Elapsed|Maximum resident' $R/owners.err | tr '\n' ' ')" >> $R/dump.txt
    if grep -qx "$rid" $W/KEEP-DUMPS 2>/dev/null; then echo "kept" >> $R/dump.txt
    else rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt; fi
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
