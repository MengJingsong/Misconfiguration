#!/usr/bin/env bash
# R25 (copied from R19, paths /mydata/r25; 2026-11-24). R19 batch runner (from R11 batch.sh): runs "name type N [RATE] [CL] [LOADCAP] [VX] [RX]"
# lines from a file in order; no arm starts at or after T0 + 6:00 (design §2.9) or when /mydata/r25-evidence/STOP exists.
# Attempt 3 (2026-11-24): T0 = 20:10:00 EST (resumption after the API-limit pause; locks held since 18:02 EST) -> limit
# 2026-11-25 02:10:00 EST. Writes its PID to /mydata/r25-evidence/DRIVER.pid and removes it at the end.
#   batch.sh <armsfile>   (setsid nohup; log to stdout)   RATE "-" = uncapped; other "-" fields = default
E=/mydata/r25-evidence; F=$1; LIMIT=1795590600
echo $$ > $E/DRIVER.pid; trap 'rm -f $E/DRIVER.pid' EXIT
while read -r name ty n rate cl lc vx rx; do
  [ -z "$name" ] && continue; case $name in \#*) continue;; esac
  if [ "$(date +%s)" -ge "$LIMIT" ]; then echo "[$(TZ=America/New_York date +%T)] last-arm rule (T0 + 6:00): $name not started"; break; fi
  [ -e $E/STOP ] && { echo "STOP file: $name not started"; break; }
  [ "${rate:--}" = - ] && rate=""; [ "${cl:--}" = - ] && cl=ONE; [ "${lc:--}" = - ] && lc=""; [ "${vx:--}" = - ] && vx=2G; [ "${rx:--}" = - ] && rx=2G
  echo "[$(TZ=America/New_York date +%T)] start $name $ty N=$n rate=${rate:-uncapped} CL=$cl $vx $rx"
  RATE=$rate CL=$cl LOADCAP=$lc VX=$vx RX=$rx bash $E/h/arm.sh $name $ty $n < /dev/null
  echo "[$(TZ=America/New_York date +%T)] end $name rc=$?"
done < $F
echo "[$(TZ=America/New_York date +%T)] BATCH DONE"
