#!/usr/bin/env bash
# U14 3-b, part 3 (19:00 EST): when R2's node dies, keep a copy of its tmpfs data (/dev/shm/3b-u14/run -> -R2keep) before
# run.py's finish() removes it; after plan3b-2.sh exits (plan.stop set, so it stops after R2): RS2 = restart on R2's data at
# its OOM table count (10 min), then R3 with its wall cap clipped to end by 20:25 EST (4 h case cap 20:33).
W=/mydata/s4/3b-U14
export U14_SHM=1
until grep -q "node_dead_ms" $W/logs/R2/session.log || grep -qE "\] (DONE|FAIL)" $W/logs/R2/session.log; do sleep 1; done
if grep -q "node_dead_ms" $W/logs/R2/session.log; then cp -a /dev/shm/3b-u14/run /dev/shm/3b-u14-R2keep && echo "$(TZ=America/New_York date '+%F %T') kept R2 data"; fi
while pgrep -f "bash harness/plan3b-2.sh" > /dev/null; do sleep 2; done
step() { echo "$(TZ=America/New_York date '+%F %T') start $*"; }
endd() { echo "$(TZ=America/New_York date '+%F %T') end $1 rc=$2"; rm -f $W/dumps/$1/*.hprof; }
rm -f $W/plan.stop
if [ -d /dev/shm/3b-u14-R2keep ]; then
  rm -rf /dev/shm/3b-u14 $W/run; mkdir -p /dev/shm/3b-u14; mv /dev/shm/3b-u14-R2keep /dev/shm/3b-u14/run
  step RS2; KEEP_RUN=1 python3 -I $W/harness/run.py restart RS2 10 > $W/logs/RS2.out 2>&1; endd RS2 $?
fi
rm -rf $W/run /dev/shm/3b-u14
left=$(( $(TZ=America/New_York date -d 'today 20:25' +%s) - $(date +%s) - 300 ))
[ $left -lt 1800 ] && { echo "skip R3: only $left s left before 20:25 EST"; exit 0; }
wc=$(( left < 6300 ? left : 6300 ))
step R3 "wall_cap=$wc"; U14_DDL_CAP=6000 U14_WALL_CAP=$wc U14_NO_SL=1 python3 -I $W/harness/run.py life R3 T 2G long 6500 > $W/logs/R3.out 2>&1; endd R3 $?
echo "$(TZ=America/New_York date '+%F %T') chain3 done"
