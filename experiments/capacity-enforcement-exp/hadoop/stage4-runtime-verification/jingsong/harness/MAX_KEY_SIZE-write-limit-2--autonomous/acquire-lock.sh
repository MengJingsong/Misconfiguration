#!/usr/bin/env bash
# Poll every 2 min for up to 60 min for the pc99 node lock; acquire atomically with mkdir.
for i in $(seq 0 30); do
  if ssh -o BatchMode=yes pc99 'mkdir /mydata/s4/NODE-LOCK 2>/dev/null && echo "jingsong-o6-stage4 $(date)" > /mydata/s4/NODE-LOCK/owner'; then
    echo "ACQUIRED at $(date) attempt $i"; ssh pc99 cat /mydata/s4/NODE-LOCK/owner; exit 0
  fi
  echo "held at $(date): $(ssh pc99 cat /mydata/s4/NODE-LOCK/owner 2>&1)"
  [ "$i" -lt 30 ] && sleep 120
done
echo "BLOCKED after 60 min"; exit 1
