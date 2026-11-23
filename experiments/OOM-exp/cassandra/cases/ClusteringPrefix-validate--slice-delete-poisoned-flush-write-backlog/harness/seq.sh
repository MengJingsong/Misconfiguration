#!/bin/bash
# U15: run the listed runs one after another (one measured node at a time). usage: bash seq.sh "<label> <heap> <arm> [wmax]" ...
# Does not start a run if /mydata/s4/u15/STOP exists or the New York clock is at/after 13:15 (design §2.5 stopping budget).
H=$(dirname "$(readlink -f "$0")"); S=/mydata/s4/u15/seq.log
for spec in "$@"; do
  [ -f /mydata/s4/u15/STOP ] && { echo "$(TZ=America/New_York date +%T) STOP file, not starting $spec" >> $S; break; }
  hm=$(TZ=America/New_York date +%H%M); [ "$hm" -ge 1315 ] && { echo "$(TZ=America/New_York date +%T) past 13:15, not starting $spec" >> $S; break; }
  echo "$(TZ=America/New_York date +%T) start $spec" >> $S
  bash "$H/run.sh" $spec
  echo "$(TZ=America/New_York date +%T) end $spec: $(cat /mydata/s4/u15/${spec%% *}/DONE 2>/dev/null)" >> $S
  sleep 5
done
echo "$(TZ=America/New_York date +%T) seq done" >> $S
