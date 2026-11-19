#!/usr/bin/env bash
# U7: small per-run excerpts for the case folder's logs/ (full logs stay on the node under /mydata/s4/u7-w4/runs/).
# Usage (on the node): excerpt.sh <out dir>; then copy <out dir> to <case folder>/logs/.
W=/mydata/s4/u7-w4/runs; O=$1; mkdir -p $O
cp $W/series-*.log $W/list-*.txt $O/ 2>/dev/null
for R in $W/*/; do
  r=$(basename $R); [ -e $R/driver.txt ] || continue; mkdir -p $O/$r
  for f in driver.txt client.txt summary.txt settings.txt conf-md5.txt oome-thread.txt dump.txt class-histo.txt threads.txt; do
    [ -e $R/$f ] && cp $R/$f $O/$r/
  done
  [ -e $R/histo.txt ] && head -45 $R/histo.txt > $O/$r/histo-head.txt
  grep -E "MaxHeapSize|MaxDirectMemorySize|HeapDumpOnOutOfMemoryError|UseG1GC|AlwaysPreTouch|open files" $R/vm-flags.txt > $O/$r/vm-flags-excerpt.txt 2>/dev/null
  grep -n -E "OutOfMemoryError|Dumping heap|Heap dump file|Executing|ERROR" $R/stdout.txt | cut -c1-400 | head -20 > $O/$r/stdout-endpoint.txt
  cat $R/gc.log* 2>/dev/null | grep -E "GC\([0-9]+\) Pause" | tail -25 > $O/$r/gc-tail.txt
  tail -15 $R/heapinfo.txt 2>/dev/null | cut -c1-260 > $O/$r/heapinfo-tail.txt
  sed -i 's/,ERR//g' $O/$r/summary.txt
done
du -sh $O
