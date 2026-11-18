#!/usr/bin/env bash
# R7: for each finished arm, count System.gc() (Bits.reserveMemory forced GCs) in V's gc.log and the worst-60 s STW
# share (gcwin.py) on ms0625; store in the driver mirror as forced-gc.txt.
M=/mydata/s4/r7-w1/mirror; R=/mydata/s4/r7-w1/runs
for d in $M/*/; do n=$(basename $d); [ -f $d/outcome.txt ] || continue; [ -s $d/forced-gc.txt ] && continue
  ssh ms0625 "cat $R/$n/V-logs/gc.log* 2>/dev/null | grep -c 'System.gc()'; python3 /mydata/s4/r7-w1/h/gcwin.py $R/$n/V-logs 2>&1 | paste -sd ' '" < /dev/null > $d/forced-gc.txt; done
