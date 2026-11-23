#!/bin/bash
# U13: run the lines of a plan file in order (one run at a time): "<label> <heap> <direct> <arm>". No run starts at or
# after 13:15 EST (design §2.7). A file /mydata/s4/u13/STOPQUEUE stops the queue before the next run.
# usage: ( setsid nohup bash queue.sh <plan> < /dev/null > /dev/null 2>&1 & ); log /mydata/s4/u13/queue.log
H=$(dirname "$(readlink -f "$0")")
Q=/mydata/s4/u13/queue.log
while read -r LABEL HEAP DIRECT ARM; do
  [ -z "$LABEL" ] && continue
  case "$LABEL" in \#*) continue;; esac
  [ -f /mydata/s4/u13/STOPQUEUE ] && { echo "$(TZ=America/New_York date +%T) STOPQUEUE before $LABEL" >> $Q; break; }
  NOW=$(TZ=America/New_York date +%H%M)
  if [ "$NOW" -ge 1315 ]; then echo "$(TZ=America/New_York date +%T) 13:15 reached, not starting $LABEL" >> $Q; break; fi
  echo "$(TZ=America/New_York date +%T) start $LABEL $HEAP $DIRECT $ARM" >> $Q
  bash "$H/run.sh" "$LABEL" "$HEAP" "$DIRECT" "$ARM"
  echo "$(TZ=America/New_York date +%T) end $LABEL: $(cat /mydata/s4/u13/$LABEL/DONE 2>/dev/null)" >> $Q
  sleep 5
done < "$1"
echo "$(TZ=America/New_York date +%T) queue done" >> $Q
