#!/usr/bin/env bash
# R11 batch runner on pc96: runs "name type G [VX RX LOADCAP]" lines from a file in order; no arm starts after 16:50 EST
# (design §2.9) or when /mydata/r11-evidence/STOP exists.   batch.sh <armsfile>   (setsid nohup; log batch-<file>.log)
E=/mydata/r11-evidence; F=$1
while read -r name ty g vx rx lc; do
  [ -z "$name" ] && continue; case $name in \#*) continue;; esac
  hm=$(TZ=America/New_York date +%H%M); if [ "$hm" -ge 1650 ]; then echo "[$hm] last-arm rule: $name not started"; break; fi
  [ -e $E/STOP ] && { echo "STOP file: $name not started"; break; }
  echo "[$(TZ=America/New_York date +%T)] start $name $ty G=$g ${vx:-2G} ${rx:-2G}"
  VX=${vx:-2G} RX=${rx:-2G} LOADCAP=${lc:-120} bash $E/h/arm.sh $name $ty $g < /dev/null
  echo "[$(TZ=America/New_York date +%T)] end $name rc=$?"
done < $F
echo "[$(TZ=America/New_York date +%T)] BATCH DONE"
