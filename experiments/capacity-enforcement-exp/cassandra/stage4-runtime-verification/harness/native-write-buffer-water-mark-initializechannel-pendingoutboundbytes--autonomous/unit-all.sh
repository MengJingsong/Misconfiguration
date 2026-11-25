#!/bin/bash
# B2e as amended (S4-A1, S4-A2): main grid, controls, repeats, the as-filed gate diagnostic.
set -u
H=/mydata/jingsong-cass-s4/o133/harness; OUT=/mydata/jingsong-cass-s4/o133/unit/run1
mkdir -p $OUT
run(){ $H/unit-run.sh $OUT "$1" "$2"; echo "$(date -u +%T) $1 rc=$?" >> $OUT/progress.txt; }
for Hm in 32768 1048576 67108864; do for B in 16384 65536 262144; do for K in 64 256; do
  run "h$Hm-B$B-K$K" "-Dwm.high=$Hm -Dwm.blob=$B -Dwm.k=$K"
done; done; done
run "ctl-reads-h32768-B65536-K256" "-Dwm.high=32768 -Dwm.blob=65536 -Dwm.k=256 -Dwm.clientReads=true"
for B in 65536 262144; do run "ctl-gate-autoread-B$B-K256" "-Dwm.high=32768 -Dwm.blob=$B -Dwm.k=256 -Dwm.gate=autoread"; done
for r in 1 2 3; do run "rep$r-h32768-B65536-K256" "-Dwm.high=32768 -Dwm.blob=65536 -Dwm.k=256"; done
run "diag-gate-asfiled-B65536-K256" "-Dwm.high=32768 -Dwm.blob=65536 -Dwm.k=256 -Dwm.gate=true"
echo "$(date -u +%T) ALL DONE" >> $OUT/progress.txt
