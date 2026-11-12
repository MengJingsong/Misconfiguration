#!/usr/bin/env bash
cd /mydata/oom-recheck/R2
for a in converge-r1 converge-r2 converge-r3; do
  h=$(ls logs/$a/*.hprof | head -1)
  echo "[$(date +%T)] $a $h"
  /usr/bin/time -v python3 -I tools/hprof_direct.py "$h" 30 > logs/$a/hprof-analysis.txt 2> logs/$a/hprof-analysis.err
  echo "[$(date +%T)] $a rc=$?"
done
echo DONE
