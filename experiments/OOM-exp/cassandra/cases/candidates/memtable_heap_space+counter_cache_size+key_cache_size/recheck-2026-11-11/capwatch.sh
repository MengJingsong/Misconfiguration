#!/usr/bin/env bash
# apply the design's 30-min wall cap to one arm (the harness's sample-count cap stretches when jcmd attaches block)
a=$1; S=/mydata/oom-recheck/R4/logs/$a/summary.txt; B=/mydata/oom-recheck/R4/batch3.out
until grep -q "workloads launched" $S 2>/dev/null; do sleep 5; done
t0=$(grep "workloads launched" $S | grep -o "t=[0-9]*" | cut -c3- ); T=$(( t0/1000 + 1800 ))
until [ $(date +%s) -ge $T ] || grep -q "ARM $a DONE" $B; do sleep 5; done
if ! grep -q "ARM $a DONE" $B && pgrep -f "[o]rg.apache.cassandra.stress.Stress" >/dev/null; then
  echo "$(date "+%F %T") manual 30-min wall cap applied to $a: stopping stress clients" | tee -a /mydata/oom-recheck/R4/logs/$a/manual-cap.txt
  pkill -f "[o]rg.apache.cassandra.stress.Stress"
fi
echo "capwatch $a done $(date +%T)"
