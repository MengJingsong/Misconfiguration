#!/usr/bin/env bash
# B21: wait (bounded) until lifetime <label> has ended (END/INVALID line in runs/<label>.out, or its script is gone).
#   wait-end.sh <label> <max_secs>
ROOT=/mydata/s4/3b-B21; L=$1; M=${2:-900}; t=0
while [ $t -lt $M ]; do
  grep -qE "END $L |INVALID|REFUSE|LOADDONE" $ROOT/runs/$L.out 2>/dev/null && break
  pgrep -f "[h]arness/[a-z-]*\.sh $L( |$)" >/dev/null || { sleep 2; break; }
  sleep 5; t=$((t+5))
done
tail -5 $ROOT/runs/$L.out | cut -c1-300
