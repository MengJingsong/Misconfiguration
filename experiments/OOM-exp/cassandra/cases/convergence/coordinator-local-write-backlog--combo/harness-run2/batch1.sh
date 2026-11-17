#!/usr/bin/env bash
# S2 run 2 batch 1 (design §3): positive control A x3 (new sampler; A-2G-r1 was the shakedown arm), then G1 / G2 interleaved x3.
cd /mydata/s2r2-evidence/h; export LOAD=90 OBS=60
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
pp(){ for n in V R1 R2; do h=$([ $n = V ] && echo ms0640 || { [ $n = R1 ] && echo ms0604 || echo ms0611; }); nohup ./dumpparse.sh $1 $n $h >/dev/null 2>&1 & done; }
for r in 2 3 4; do late && break; RX1=8G ./arm.sh A-2G-r$r A 2G 2>&1 | tail -1; pp A-2G-r$r; done
for r in 1 2 3; do
  late && break; RX1=2G RX2=2G ./arm.sh G1-2G-r$r G 2G 2>&1 | tail -1; pp G1-2G-r$r
  late && break; RX1=8G RX2=8G ./arm.sh G2-2G-r$r G 2G 2>&1 | tail -1; pp G2-2G-r$r
done
echo BATCH1_DONE
