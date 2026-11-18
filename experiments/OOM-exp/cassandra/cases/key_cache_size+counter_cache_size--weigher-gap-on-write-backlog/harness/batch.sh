#!/usr/bin/env bash
# R8 batch runner on pc91: runs "name type N [VX]" lines from a file in order; stops at the 01:55 EST last-arm rule.
#   batch.sh <armsfile>        (launched with setsid nohup; log in /mydata/s4/r8-w1/runs/batch-<file>.log)
W=/mydata/s4/r8-w1; F=$1
while read -r name ty n vx; do
  [ -z "$name" ] && continue; case $name in \#*) continue;; esac
  hm=$(TZ=America/New_York date +%H%M); if [ "$hm" -ge 0155 ] && [ "$hm" -lt 1200 ]; then echo "[$hm] last-arm rule: $name not started"; break; fi
  [ -e $W/STOP ] && { echo "STOP file: $name not started"; break; }
  echo "[$(TZ=America/New_York date +%T)] start $name $ty $n ${vx:-2G}"
  VX=${vx:-2G} $W/h/arm.sh $name $ty $n
  echo "[$(TZ=America/New_York date +%T)] end $name rc=$?"
done < $F
echo "[$(TZ=America/New_York date +%T)] BATCH DONE"
