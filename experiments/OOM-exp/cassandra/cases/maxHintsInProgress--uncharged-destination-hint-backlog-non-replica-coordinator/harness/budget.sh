#!/bin/bash
# B23 budget search (design §2.9): after the T/C/I sequence ends, T at 4 GiB (N 200,000), then 8 GiB and 15,872 MiB
# (N 400,000), stepping up only while the previous budget reached an OOM. Log: /mydata/s4/b23/seq.log
S=/mydata/s4/b23/seq.log
until grep -q "seq done" $S; do sleep 10; done
for spec in "B4G 4G T 200000" "B8G 8G T 400000" "B15872M 15872M T 400000"; do
  [ -f /mydata/s4/b23/STOP ] && { echo "$(TZ=America/New_York date +%T) STOP file, not starting $spec" >> $S; break; }
  echo "$(TZ=America/New_York date +%T) start $spec" >> $S
  bash /mydata/s4/b23/harness/run.sh $spec
  L=${spec%% *}
  echo "$(TZ=America/New_York date +%T) end $spec: $(cat /mydata/s4/b23/$L/DONE 2>/dev/null)" >> $S
  [ -s /mydata/s4/b23/$L/logs/oom-grep.txt ] || { echo "$(TZ=America/New_York date +%T) no OOM at $L: boundary, stop stepping" >> $S; break; }
  sleep 5
done
echo "$(TZ=America/New_York date +%T) budget done" >> $S
