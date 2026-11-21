#!/usr/bin/env bash
# R19 batch runner on pc96 (from R11 batch.sh): runs "name type N [RATE] [CL] [LOADCAP] [VX] [RX]" lines from a file in
# order; no arm starts at or after 06:45 EST (design §2.9) or when /mydata/r19-evidence/STOP exists.
#   batch.sh <armsfile>   (setsid nohup; log to stdout)   RATE "-" = uncapped; other "-" fields = default
E=/mydata/r19-evidence; F=$1
while read -r name ty n rate cl lc vx rx; do
  [ -z "$name" ] && continue; case $name in \#*) continue;; esac
  hm=$(TZ=America/New_York date +%H%M); if [ "$((10#$hm))" -ge 645 ] && [ "$((10#$hm))" -lt 1200 ]; then echo "[$hm] last-arm rule: $name not started"; break; fi
  [ -e $E/STOP ] && { echo "STOP file: $name not started"; break; }
  [ "${rate:--}" = - ] && rate=""; [ "${cl:--}" = - ] && cl=ONE; [ "${lc:--}" = - ] && lc=""; [ "${vx:--}" = - ] && vx=2G; [ "${rx:--}" = - ] && rx=2G
  echo "[$(TZ=America/New_York date +%T)] start $name $ty N=$n rate=${rate:-uncapped} CL=$cl $vx $rx"
  RATE=$rate CL=$cl LOADCAP=$lc VX=$vx RX=$rx bash $E/h/arm.sh $name $ty $n < /dev/null
  echo "[$(TZ=America/New_York date +%T)] end $name rc=$?"
done < $F
echo "[$(TZ=America/New_York date +%T)] BATCH DONE"
