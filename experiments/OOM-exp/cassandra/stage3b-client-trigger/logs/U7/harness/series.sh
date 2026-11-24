#!/usr/bin/env bash
# U7 stage 3-b confirm copy (2026-11-23): work dir /mydata/s4/3b-U7, no time-of-day cutoff (the task's 4-h cap is kept by
# the session), every dump deleted after the OOME-thread parse and histogram.
# U7 series: run.sh for each "<rid> <conf> <heap> <step> [<step> ...]" line of the list file, in order; after each run
# that left an .hprof: OOME thread (inline), then histogram (inline unless 'nohisto' is the list line's last word), dump deleted
# unless the rid is T-1 (kept to the end of the session). No run starts at/after 17:40 America/New_York (§2.7);
# resumed session 2026-11-18 (§3.2 item 6): the cutoff is U7_CUTOFF (HHMM ET) when set.
W=/mydata/s4/3b-U7; H=$W/harness; LIST=$1; LOG=$W/runs/series-$(basename $LIST).log
while read -r line; do
  [ -z "$line" ] && continue
  case "$line" in \#*) continue;; esac
  set -- $line; rid=$1; histo=yes
  [ "${!#}" = nohisto ] && { histo=no; set -- "${@:1:$(($#-1))}"; }
  [ -e $W/runs/SERIES-STOP ] && { echo "$(date +%FT%T) SKIP $rid (SERIES-STOP)" >> $LOG; continue; }
  echo "$(date +%FT%T) START $line" >> $LOG
  bash $H/run.sh "$@"
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt
    timeout 600 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1
    [ $histo = yes ] && timeout 1500 python3 -I $H/hprof-histo.py $f --top 30 --value-len 4 > $R/histo.txt 2>&1
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt)" >> $LOG
done < $LIST
echo "$(date +%FT%T) SERIES DONE" >> $LOG
