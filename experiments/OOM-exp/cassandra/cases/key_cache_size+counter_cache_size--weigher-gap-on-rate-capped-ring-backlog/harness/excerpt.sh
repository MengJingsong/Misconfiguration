#!/usr/bin/env bash
# R19: small per-arm excerpts for the case folder's logs/<arm>/ (run on pc96 after an arm).   excerpt.sh <arm> <dest dir>
A=$1; S=/mydata/r19-evidence/runs/$A; D=$2/$A; mkdir -p $D
cp $S/arm.log $S/hstop.txt $S/obs-result $S/V-cmdline.txt $D/ 2>/dev/null
for n in V R1 R2; do cp $S/$n/outcome.txt $D/$n-outcome.txt 2>/dev/null; done
cp $S/V/oom-excerpt.txt $D/V-oom-excerpt.txt 2>/dev/null; [ -s $D/V-oom-excerpt.txt ] || rm -f $D/V-oom-excerpt.txt
cp $S/V/V-yaml.diff $D/ 2>/dev/null; cp $S/V/dump-hist.txt $S/V/dump.ls $D/ 2>/dev/null
head -45 $S/V/hist-pre.txt > $D/hist-pre-top.txt 2>/dev/null; tail -1 $S/V/hist-pre.txt >> $D/hist-pre-top.txt 2>/dev/null
grep -E '^TOTAL_REACHED|^FIRST_SEND|^FINAL' $S/client/load.log > $D/load.txt; grep -E 'epochMs=.* t=' $S/client/load.log | cut -c1-160 | head -150 >> $D/load.txt
fs=$(grep -oP '^FIRST_SEND epochMs=\K\d+' $S/client/load.log)
awk -v t0=$fs '$2 ~ /^pending=/ {split($2,a,"="); s=int(($1-t0)/1000); if (!(s in m) || a[2]>m[s]) m[s]=a[2]; if (s>mx) mx=s} END {for (i=-2;i<=mx;i++) if (i in m) printf "%+d s max pending %d\n", i, m[i]}' $S/V/gate.log | head -400 > $D/gate-pending-1s.txt
awk -v t0=$((fs/1000)) '{s=$1-t0; if (s>=-5 && s<=400) print s" "$0}' $S/V/poll.log | cut -c1-400 > $D/V-poll-burst.txt
for n in R1 R2; do grep -oE '^[0-9]+ heapMiB=[0-9/]+ mut_pending=[0-9-]+' $S/$n/poll.log | awk -v t0=$((fs/1000)) '{s=$1-t0; if (s>=-5 && s<=400) print s" "$0}' > $D/$n-poll-pending.txt; done
cp $S/obs.log $D/obs.log 2>/dev/null
