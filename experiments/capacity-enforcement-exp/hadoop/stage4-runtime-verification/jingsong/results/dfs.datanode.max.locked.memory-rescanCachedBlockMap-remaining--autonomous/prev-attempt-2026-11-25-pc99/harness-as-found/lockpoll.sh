#!/usr/bin/env bash
# Poll the pc99 node lock every 2 min for up to 60 min; acquire it when free.
for i in $(seq 0 30); do
  if ssh -o BatchMode=yes -o ConnectTimeout=15 pc99 'mkdir /mydata/s4/NODE-LOCK 2>/dev/null && echo "o22-stage4-agent $(date)" > /mydata/s4/NODE-LOCK/owner'; then
    echo "ACQUIRED at $(date) after $i polls"; exit 0
  fi
  echo "$(date '+%T') held by: $(ssh pc99 cat /mydata/s4/NODE-LOCK/owner 2>/dev/null)"
  [ $i -lt 30 ] && sleep 120
done
echo "BLOCKED: lock still held after 60 min"; exit 3
