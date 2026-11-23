#!/usr/bin/env bash
# Run arms from a queue file, one per line: name|kind|xmx|dump|vextra|build  (stops on /mydata/s4/B19/STOP)
#   queue.sh <queuefile>   -> log /mydata/s4/B19/runs/queue.log
Q=$1; H=/mydata/s4/B19/h
while IFS='|' read -r name kind xmx dump vextra build; do
  [ -z "$name" ] && continue; [[ "$name" == \#* ]] && continue
  [ -e /mydata/s4/B19/STOP ] && { echo "STOP file present, queue halted before $name"; break; }
  echo "$(TZ=America/New_York date +%T) START $name"
  bash "$H/arm.sh" "$name" "$kind" "$xmx" "$dump" "$vextra" "${build:-/mydata/s4/cassandra-base}"
  echo "$(TZ=America/New_York date +%T) END $name"
done < "$Q"
echo "$(TZ=America/New_York date +%T) QUEUE_DONE $Q"
