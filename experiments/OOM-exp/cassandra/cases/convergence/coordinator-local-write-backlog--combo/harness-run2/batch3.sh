#!/usr/bin/env bash
# S2 run 2 batch 3 (amendment R2-A1/A2): upward heap search G1 at 4 GiB (all three nodes 4 GiB) x3, then the equal-heap
# RF=2 longer burst (A topology, R1 2 GiB, LOAD=300) x3. Starts after batch 2; no arm starts after 01:35 EST.
cd /mydata/s2r2-evidence/h; export OBS=60
while pgrep -f "[b]atch2.sh" >/dev/null; do sleep 10; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
pp(){ for n in V R1 R2; do h=$([ $n = V ] && echo ms0640 || { [ $n = R1 ] && echo ms0604 || echo ms0611; }); nohup ./dumpparse.sh $1 $n $h >/dev/null 2>&1 & done; }
for r in 1 2 3; do late && break; LOAD=90 RX1=4G RX2=4G ./arm.sh G1-4G-r$r G 4G 2>&1 | tail -1; pp G1-4G-r$r; done
for r in 1 2 3; do late && break; LOAD=300 RX1=2G ./arm.sh Eeq-2G-long-r$r A 2G 2>&1 | tail -1; pp Eeq-2G-long-r$r; done
echo BATCH3_DONE
