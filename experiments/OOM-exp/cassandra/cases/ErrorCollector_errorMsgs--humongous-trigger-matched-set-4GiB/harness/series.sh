#!/usr/bin/env bash
# R20 series (from R15's, 2026-11-21): run.sh for each
# "<rid> <build> <heap> <payload> <N> <k1> <trig-spec> <hold> <histo|-> [len|-] [tmax] [k2] [trig2-spec|-] [diag|-]"
# line of the list file, in order; dump analysis after each run that left an .hprof (OOME thread always; histogram if
# 'histo'; each capped at 15 min), then the .hprof is deleted. No run starts at/after 06:45 America/New_York.
# 'diag' sets R20_DIAG=1 (full thread dumps every 10 s). A file runs/SKIP-<rid> skips that run (checkpoint re-plans).
# "SKIPIF-FEWOOM <n> <rid...>" skips to ENDSKIP when fewer than n of the listed runs ended in an OOM;
# "SKIPIF-AFTER <HHMM>" skips to ENDSKIP when the ET clock is at or after HHMM. Skip blocks do not nest (ENDSKIP clears).
# A line "SKIPIF-SURVIVED <rid>" (or "SKIPIF-OOM <rid>") skips the following lines up to the next "ENDSKIP" when <rid> ended without an OOM (with an OOM).
W=/mydata/s4/r20; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
skip=""
while read -r rid build heap arm n k tspec hold histo len tmax k2 t2spec diag; do
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
  if [ "$rid" = SKIPIF-FEWOOM ]; then
    c=0; for r in $heap $arm $n $k $tspec; do grep -q "oom:" $W/runs/$r/driver.txt 2>/dev/null && c=$((c+1)); done
    if [ "$c" -lt "$build" ]; then skip=1; echo "$(date +%FT%T) skip rule: $c OOM < $build" >> $LOG; fi
    continue
  fi
  if [ "$rid" = SKIPIF-AFTER ]; then
    now=$(TZ=America/New_York date +%H%M)
    if [ "$now" -ge "$build" ] && [ "$now" -lt 1200 ]; then skip=1; echo "$(date +%FT%T) skip rule: ET $now >= $build" >> $LOG; fi
    continue
  fi
  [ "$rid" = ENDSKIP ] && { skip=""; continue; }
  [ -n "$skip" ] && { echo "$(date +%FT%T) SKIP $rid (skip rule)" >> $LOG; continue; }
  [ -e $W/runs/SKIP-$rid ] && { echo "$(date +%FT%T) SKIP $rid (SKIP file)" >> $LOG; continue; }
  [ -e $W/runs/HALT ] && { echo "$(date +%FT%T) SKIP $rid (HALT file)" >> $LOG; continue; }
  now=$(TZ=America/New_York date +%H%M)
  if [ "$now" -ge 645 ] && [ "$now" -lt 1200 ]; then echo "$(date +%FT%T) SKIP $rid (ET $now >= 0645)" >> $LOG; continue; fi
  echo "$(date +%FT%T) START $rid" >> $LOG
  DG=""; [ "$diag" = diag ] && DG=1
  R20_DIAG=$DG bash $H/run.sh $rid $build $heap $arm $n $k $tspec $hold ${len:--} ${tmax:-300} ${k2:-0} ${t2spec:--}
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
