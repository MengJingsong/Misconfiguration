#!/bin/bash
# U11: run the listed runs one after another (one measured node at a time). usage: bash seq.sh "<label> <heap> <arm>" ...
# stops before starting a run if the file /mydata/s4/u11-w4/STOP exists or the New York clock is past 17:35.
H=$(dirname "$(readlink -f "$0")")
for spec in "$@"; do
  [ -f /mydata/s4/u11-w4/STOP ] && { echo "$(date +%T) STOP file, not starting $spec" >> /mydata/s4/u11-w4/seq.log; break; }
  hm=$(TZ=America/New_York date +%H%M); [ "$hm" -ge 1735 ] && { echo "$(date +%T) past 17:35, not starting $spec" >> /mydata/s4/u11-w4/seq.log; break; }
  echo "$(TZ=America/New_York date +%T) start $spec" >> /mydata/s4/u11-w4/seq.log
  bash "$H/run.sh" $spec
  echo "$(TZ=America/New_York date +%T) end $spec: $(cat /mydata/s4/u11-w4/${spec%% *}/DONE 2>/dev/null)" >> /mydata/s4/u11-w4/seq.log
  sleep 5
done
echo "$(TZ=America/New_York date +%T) seq done" >> /mydata/s4/u11-w4/seq.log
