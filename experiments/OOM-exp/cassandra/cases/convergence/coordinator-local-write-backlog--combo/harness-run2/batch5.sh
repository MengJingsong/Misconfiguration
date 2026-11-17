#!/usr/bin/env bash
# S2 run 2 batch 5 (amendment R2-A4): G1 at 4 GiB (all nodes) with a 300 s observation after the client exits, x3.
cd /mydata/s2r2-evidence/h; export LOAD=90 OBS=300
while pgrep -f "[b]atch4.sh" >/dev/null; do sleep 10; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
pp(){ for n in V R1 R2; do h=$([ $n = V ] && echo ms0640 || { [ $n = R1 ] && echo ms0604 || echo ms0611; }); nohup ./dumpparse.sh $1 $n $h >/dev/null 2>&1 & done; }
for r in 1 2 3; do late && break; RX1=4G RX2=4G ./arm.sh G1-4G-obs300-r$r G 4G 2>&1 | tail -1; pp G1-4G-obs300-r$r; done
echo BATCH5_DONE
