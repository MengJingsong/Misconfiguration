#!/usr/bin/env bash
# B22 side instrument (added 2026-11-21 08:45 EST, after T-1/T-2 showed "LARGE_MESSAGES ... overloaded; dropping" warnings):
# every 10 s, nodetool netstats on node 1 (7199) and node 2 (7299): the "Large messages" pending/completed/dropped line
# (outbound, per node). Read-only JMX; stops at the stop file or after 5 h.
ROOT=/mydata/s4/b22; NT=$ROOT/tree/bin/nodetool; OUT=$ROOT/netpoll.csv; END=$(( $(date +%s) + 18000 ))
[ -f $OUT ] || echo "epoch,node,large_active,large_pending,large_completed,large_dropped,run" > $OUT
while [ ! -f $ROOT/netpoll.stop ] && [ $(date +%s) -lt $END ]; do
  run=$(ls -td $ROOT/runs/*/ 2>/dev/null | head -1 | xargs basename)
  for p in 7199 7299; do
    l=$(timeout 8 $NT -h 127.0.0.1 -p $p netstats 2>/dev/null | awk '/^Large messages/{print $3","$4","$5","$6}')
    [ -n "$l" ] && echo "$(date +%s),$p,$l,$run" >> $OUT
  done
  sleep 10
done
