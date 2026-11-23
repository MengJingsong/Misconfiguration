#!/usr/bin/env bash
# analyze dumps: dumps.sh <armdir>...  -> <armdir>/hprofhist.txt, oome-thread.txt
for R in "$@"; do f=$(ls $R/*.hprof 2>/dev/null | head -1); [ -z "$f" ] && continue
  taskset -c 6-7 python3 -I /mydata/s4/B19/h/hprofhist.py "$f" 30 > $R/hprofhist.txt 2>&1
  taskset -c 6-7 python3 -I /mydata/s4/B19/h/hprof_oome_thread.py "$f" 30 > $R/oome-thread.txt 2>&1
  echo "done $R"; done; echo DUMPS_DONE
