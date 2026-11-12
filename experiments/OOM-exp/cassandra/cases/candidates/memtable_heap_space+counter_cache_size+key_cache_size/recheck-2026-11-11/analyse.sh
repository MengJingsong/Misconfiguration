#!/usr/bin/env bash
# usage: analyse.sh ARM...  runs tools/hprof_holders.py on each arm's OOM dump, niced
cd /mydata/oom-recheck/R4/logs
for a in "$@"; do
  d=$(ls $a/node-logs/*.hprof 2>/dev/null | head -1); [ -n "$d" ] || { echo "$a: no dump"; continue; }
  nice -n 19 python3 -I ../tools/hprof_holders.py "$d" 40 > $a/hprof-report.txt 2> $a/hprof-report.err
  echo "$a: analysed rc=$? $(date +%T)"
done
echo ANALYSE DONE
