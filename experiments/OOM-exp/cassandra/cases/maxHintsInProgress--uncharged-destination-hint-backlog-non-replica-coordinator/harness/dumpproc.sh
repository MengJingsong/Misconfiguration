#!/bin/bash
# B23: histogram of a run's heap dump(s) with hprofhist.py, then delete the dump unless <keep> = 1. usage: bash dumpproc.sh <run dir> <keep>
R=$1; K=$2
for f in "$R"/dump/*.hprof; do
  [ -f "$f" ] || continue
  ls -la "$f" > "$R/logs/hprofhist.txt"
  python3 -I /mydata/s4/b23/harness/hprofhist.py "$f" 30 >> "$R/logs/hprofhist.txt" 2>&1
  if [ "$K" = 1 ]; then echo "kept: $f" >> "$R/logs/hprofhist.txt"; else rm -f "$f"; echo "deleted: $f" >> "$R/logs/hprofhist.txt"; fi
done
touch "$R/logs/hprofhist.done"
