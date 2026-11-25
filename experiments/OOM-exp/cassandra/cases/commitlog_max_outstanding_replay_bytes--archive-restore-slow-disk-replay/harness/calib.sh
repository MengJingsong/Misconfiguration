#!/usr/bin/env bash
# R23 S0.3 disk calibration (uncounted): for D in 0 100 300 1000 ms: dd 64 MiB conv=fsync (s, MiB/s) and ten 4 KiB
# conv=fsync writes to fresh files (mean/max ms). Then D = 0, rm vol/cal*. Output: runs/calib/calib.txt
set -uo pipefail
source /mydata/s4/r23/harness/common.sh
O=$W/runs/calib; mkdir -p $O; LOG=$O/calib.txt
for D in 0 100 300 1000; do
  $H/slowdisk.sh set $D >> $LOG
  sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
  t0=$(date +%s.%N); dd if=/dev/zero of=$W/vol/cal bs=1M count=64 conv=fsync 2>/dev/null; t1=$(date +%s.%N)
  big=$(python3 -c "print(f'{$t1-$t0:.2f} s, {64/($t1-$t0):.1f} MiB/s')")
  lat=""
  for i in $(seq 1 10); do a=$(date +%s.%N); dd if=/dev/zero of=$W/vol/cal4k-$i bs=4k count=1 conv=fsync 2>/dev/null; b=$(date +%s.%N); lat="$lat $(python3 -c "print(round(($b-$a)*1000))")"; done
  st=$(python3 -c "l=[int(x) for x in '$lat'.split()]; print(f'mean {sum(l)/len(l):.0f} ms, max {max(l)} ms')")
  log "D=${D} ms: 64 MiB conv=fsync: $big; 4 KiB conv=fsync x10: $st (each:$lat)"
  rm -f $W/vol/cal $W/vol/cal4k-*
done
$H/slowdisk.sh set 0 >> $LOG
rm -f $W/vol/cal*
