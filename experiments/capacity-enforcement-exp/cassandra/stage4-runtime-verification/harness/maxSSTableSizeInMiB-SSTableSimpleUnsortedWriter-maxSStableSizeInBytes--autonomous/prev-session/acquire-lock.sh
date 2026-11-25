#!/bin/bash
# poll pc99 node lock every 2 min up to 60 min
for i in $(seq 0 30); do
  if ssh -o BatchMode=yes pc99 'mkdir /mydata/s4/NODE-LOCK 2>/dev/null && echo "jingsong-o116-stage4 $(date)" > /mydata/s4/NODE-LOCK/owner'; then
    echo "ACQUIRED $(date) attempt=$i"; exit 0
  fi
  echo "held $(date) by: $(ssh -o BatchMode=yes pc99 'cat /mydata/s4/NODE-LOCK/owner 2>/dev/null')"
  [ $i -lt 30 ] && sleep 120
done
echo "TIMEOUT $(date)"; exit 1
