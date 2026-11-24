#!/usr/bin/env bash
# U14 3-b confirm sequence (ms0640, 2026-11-23): probe P0, then R1 (kept run dir) -> restart leg RS1 on R1's data -> R2 -> R3.
# Disk rule (case §2.5) decided by P0 (/mydata, 480 ms per CREATE) vs P0b (/dev/shm, 110 ms): U14_SHM=1 for every lifetime.
# P0 and P0b (probe + 300 tables) were run by hand before this plan.
# Each .hprof is deleted right after run.py's full scan (disk: /mydata 18 GiB free). A file $W/plan.stop stops the sequence.
W=/mydata/s4/3b-U14
export U14_SHM=1
step() { echo "$(TZ=America/New_York date '+%F %T') start $*"; }
endd() { echo "$(TZ=America/New_York date '+%F %T') end $1 rc=$2"; rm -f $W/dumps/$1/*.hprof; [ -e $W/plan.stop ] && { echo stop; exit 0; }; }
step R1; KEEP_RUN=1 python3 -I $W/harness/run.py life R1 T 2G long 6500 > $W/logs/R1.out 2>&1; endd R1 $?
step RS1; KEEP_RUN=1 python3 -I $W/harness/run.py restart RS1 20 > $W/logs/RS1.out 2>&1; endd RS1 $?
rm -rf $W/run /dev/shm/3b-u14
step R2; python3 -I $W/harness/run.py life R2 T 2G long 6500 > $W/logs/R2.out 2>&1; endd R2 $?
step R3; python3 -I $W/harness/run.py life R3 T 2G long 6500 > $W/logs/R3.out 2>&1; endd R3 $?
echo "$(TZ=America/New_York date '+%F %T') plan done"
