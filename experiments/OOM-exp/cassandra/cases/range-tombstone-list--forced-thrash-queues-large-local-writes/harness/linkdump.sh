#!/bin/bash
# R22 stage 2: hard-link the dump of run $1 (tmpfs) so run.sh deleting it leaves a copy for hprofhist.py; bounded 30 min.
for i in $(seq 1 1800); do
  f=$(ls /dev/shm/r22/dump-$1/*.hprof 2>/dev/null | head -1)
  if [ -n "$f" ]; then ln "$f" /dev/shm/r22/keep-$1.hprof && echo "linked $f $(date +%s)"; exit 0; fi
  [ -f /mydata/s4/r22/$1/DONE ] && { echo "no dump"; exit 0; }
  sleep 1
done
