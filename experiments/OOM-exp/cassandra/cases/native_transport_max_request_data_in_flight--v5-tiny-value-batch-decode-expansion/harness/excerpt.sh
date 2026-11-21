#!/usr/bin/env bash
# R13 (from B14) excerpt.sh <run-id>...: print small per-run excerpts (run on the node; output saved under logs/<run-id>.txt)
for r in "$@"; do
  R=/mydata/s4/r13-w1/runs/$r
  echo "#### $r  ($R)"
  for f in driver.txt summary.txt dump.txt resolved.txt conf-md5.txt; do [ -f $R/$f ] && { echo "--- $f"; grep -v "Full GCs" $R/$f; }; done
  [ -f $R/oome-thread.txt ] && { echo "--- oome-thread.txt (head 25)"; head -25 $R/oome-thread.txt; }
  [ -f $R/histo.txt ] && { echo "--- histo.txt"; cat $R/histo.txt; }
  echo "--- threads.txt (epoch ntr held getmut wait clog memt decode verify)"; cat $R/threads.txt
  echo "--- jmx.csv"; cat $R/jmx.csv
  echo "--- gc: Full/Young pauses (all gc.log files, by uptime; first 5 and last 25)"
  cat $R/gc.log* 2>/dev/null | grep -E "GC\([0-9]+\) Pause (Full|Young)" | sort -t'[' -k3,3 -n | awk '{print}' > /tmp/r13-gc-$r.txt
  head -5 /tmp/r13-gc-$r.txt | cut -c1-170; echo ...; tail -25 /tmp/r13-gc-$r.txt | cut -c1-170; rm -f /tmp/r13-gc-$r.txt
  echo "--- stdout OOM lines"; grep -E "OutOfMemoryError|Dumping heap|Heap dump file|kill -9" $R/stdout.txt | head -8
  echo "--- vm flags"; tr ' ' '\n' < $R/vm-flags.txt | grep -E "MaxDirectMemorySize|MaxHeapSize|G1HeapRegionSize|UseG1GC|InitialHeapSize"; grep -i "open files" $R/vm-flags.txt
  echo "--- completions: status counts"; cat $R/completions-p*.txt | awk '{print $4}' | sort | uniq -c
  echo "--- client first lines"; head -3 $R/client-p0.txt
done
