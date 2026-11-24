#!/usr/bin/env bash
# U14 3-b confirm, second part (after R1 stopped at the 40-min DDL cap; amendment in run.py): RS1 restart leg on R1's data
# (10 min), then R2 and R3 with DDL cap 6,000 s and no service-loss stop; R3's wall cap is clipped so that it ends by 20:25 EST.
W=/mydata/s4/3b-U14
export U14_SHM=1
step() { echo "$(TZ=America/New_York date '+%F %T') start $*"; }
endd() { echo "$(TZ=America/New_York date '+%F %T') end $1 rc=$2"; rm -f $W/dumps/$1/*.hprof; [ -e $W/plan.stop ] && { echo stop; exit 0; }; }
step RS1; KEEP_RUN=1 python3 -I $W/harness/run.py restart RS1 10 > $W/logs/RS1.out 2>&1; endd RS1 $?
rm -rf $W/run /dev/shm/3b-u14
step R2; U14_DDL_CAP=6000 U14_WALL_CAP=6300 U14_NO_SL=1 python3 -I $W/harness/run.py life R2 T 2G long 6500 > $W/logs/R2.out 2>&1; endd R2 $?
left=$(( $(TZ=America/New_York date -d 'today 20:25' +%s) - $(date +%s) - 300 ))
[ $left -lt 1800 ] && { echo "skip R3: only $left s left before 20:25 EST"; exit 0; }
wc=$(( left < 6300 ? left : 6300 ))
step R3 "wall_cap=$wc"; U14_DDL_CAP=6000 U14_WALL_CAP=$wc U14_NO_SL=1 python3 -I $W/harness/run.py life R3 T 2G long 6500 > $W/logs/R3.out 2>&1; endd R3 $?
echo "$(TZ=America/New_York date '+%F %T') plan done"
