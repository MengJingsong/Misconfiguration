#!/usr/bin/env bash
# S2 run 2: copy small per-arm excerpts from pc96:/mydata/s2r2-evidence/runs/<arm>/ into the case's logs-run2/arms/<arm>/.
#   excerpt.sh <dest logs-run2 dir> <arm> [<arm> ...]
D=$1; shift
for a in "$@"; do
  s=/mydata/s2r2-evidence/runs/$a; o=$D/arms/$a; mkdir -p $o
  grep -v TokenRange $s/arm.log | cut -c1-400 > $o/arm.log
  for n in V R1 R2; do [ -f $s/$n/outcome.txt ] || continue
    cp $s/$n/outcome.txt $o/$n-outcome.txt
    [ -f $s/$n/poll.log ] && awk 'NR%3==1' $s/$n/poll.log > $o/$n-poll-every9s.log
    [ -f $s/$n/dump-hist.txt ] && cp $s/$n/dump-hist.txt $o/$n-dump-hist.txt
    [ -s $s/$n/oom-excerpt.txt ] && head -8 $s/$n/oom-excerpt.txt | cut -c1-300 > $o/$n-oom-first-error.txt
    grep -h "safepoint region: HeapDumper\|safepoint region: ReportJavaOutOfMemory" $s/$n/gc.log* 2>/dev/null > $o/$n-oom-safepoints.txt; [ -s $o/$n-oom-safepoints.txt ] || rm -f $o/$n-oom-safepoints.txt
    grep -h "messages were dropped\|timeout expired before reaching the network" $s/$n/system.log 2>/dev/null | cut -c1-260 > $o/$n-drops.txt; [ -s $o/$n-drops.txt ] || rm -f $o/$n-drops.txt
  done
  grep -E "t=|FINAL" $s/client/load.log | cut -c1-200 > $o/client-load.txt
  [ -f $s/V/yaml.diff ] && cp $s/V/yaml.diff $o/V-yaml.diff
done
