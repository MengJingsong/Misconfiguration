#!/usr/bin/env bash
# R7: one line per finished arm from the driver mirror (outcome + validity + first-OOM thread/frames).
M=/mydata/s4/r7-w1/mirror
for d in $(ls -tr -d $M/*/ 2>/dev/null); do n=$(basename $d); [ -f $d/outcome.txt ] || { echo "$n: running/incomplete"; continue; }
  o=$(head -1 $d/outcome.txt | sed 's/.*platform=aarch64 | //'); v=$(grep '^valid' $d/outcome.txt)
  f=$(grep -m1 -o 'ERROR \[[^]]*\]' $d/first-oom.txt 2>/dev/null); cl=$(grep -c 'CommitLog.add' $d/first-oom.txt 2>/dev/null)
  echo "$n | $o | $v | first=$f CommitLog.add_in_first=$cl"; done
