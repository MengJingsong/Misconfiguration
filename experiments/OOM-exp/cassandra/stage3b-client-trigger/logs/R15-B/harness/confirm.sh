#!/usr/bin/env bash
# 3-b R15-B confirm series on pc82 (2026-11-24; from R20's confirm.sh): S0A (auth shakedown, not a reading), then TB2A-1 (the TB2 arm under auth),
# dump analysis (OOME thread + histogram, each capped at 15 min), .hprof deleted. A file runs/HALT stops before the next run.
# Usage: confirm.sh <run lines...> as "<rid> <build> <heap> <arm> <N> <k1> <trig-spec> <hold> <histo|-> [len] [tmax]"
W=/mydata/s4/3b-R15-B; H=$W/harness; LOG=$W/runs/series.log; mkdir -p $W/runs
for line in "$@"; do
  set -- $line; rid=$1; histo=$9
  [ -e $W/runs/HALT ] && { echo "$(date +%FT%T) SKIP $rid (HALT)" >> $LOG; continue; }
  echo "$(date +%FT%T) START $rid ($line)" >> $LOG
  bash $H/run.sh $1 $2 $3 $4 $5 $6 $7 $8 ${10:--} ${11:-300}
  R=$W/runs/$rid
  for f in $R/*.hprof; do
    [ -e "$f" ] || continue
    ls -l $f > $R/dump.txt; sha256sum $f | cut -c1-16 >> $R/dump.txt
    timeout 900 python3 -I $H/hprof_oome_thread.py $f 40 > $R/oome-thread.txt 2>&1; echo "oome-thread rc=$?" >> $R/dump.txt
    if [ "$histo" = histo ]; then timeout 900 python3 -I $H/hprof-histo.py $f --len-range 47 54 --top 30 > $R/histo.txt 2>&1; echo "histo rc=$?" >> $R/dump.txt; fi
    rm -f $f; echo "deleted after analysis $(date +%FT%T)" >> $R/dump.txt
  done
  echo "$(date +%FT%T) END $rid $(grep -m1 '^endpoint' $R/summary.txt 2>/dev/null)" >> $LOG
done
echo "$(date +%FT%T) SERIES DONE" >> $LOG
