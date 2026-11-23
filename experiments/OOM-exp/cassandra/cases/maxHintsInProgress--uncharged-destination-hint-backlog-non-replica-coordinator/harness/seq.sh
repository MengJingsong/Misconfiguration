#!/bin/bash
# B23: run the listed runs one after another (one measured cluster at a time). usage: bash seq.sh "<label> <heap> <arm> <N> [size] [threads] [extra]" ...
# Does not start a run if /mydata/s4/b23/STOP exists (run.sh itself refuses to start after 13:15 New York).
S=/mydata/s4/b23/seq.log
for spec in "$@"; do
  [ -f /mydata/s4/b23/STOP ] && { echo "$(TZ=America/New_York date +%T) STOP file, not starting $spec" >> $S; break; }
  echo "$(TZ=America/New_York date +%T) start $spec" >> $S
  bash /mydata/s4/b23/harness/run.sh $spec
  echo "$(TZ=America/New_York date +%T) end $spec: $(cat /mydata/s4/b23/${spec%% *}/DONE 2>/dev/null)" >> $S
  sleep 5
done
echo "$(TZ=America/New_York date +%T) seq done" >> $S
