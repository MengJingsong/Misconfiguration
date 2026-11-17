#!/usr/bin/env bash
# S2 run 2 batch 2 (amendment R2-A1): G1 intervention CL=ALL x3, G1 rate-cap control 1500/s x3, A CL=LOCAL_ONE x3,
# G2 CL=ALL x3 (only if G2 failed in batch 1), interleaved by repetition. Starts after batch 1.
cd /mydata/s2r2-evidence/h; export LOAD=90 OBS=60
while pgrep -f "[b]atch1.sh" >/dev/null; do sleep 10; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
pp(){ for n in V R1 R2; do h=$([ $n = V ] && echo ms0640 || { [ $n = R1 ] && echo ms0604 || echo ms0611; }); nohup ./dumpparse.sh $1 $n $h >/dev/null 2>&1 & done; }
g2fail=$(grep -l "V_DEAD" /mydata/s2r2-evidence/runs/G2-2G-r*/arm.log 2>/dev/null | wc -l)
for r in 1 2 3; do
  late && break; CL=ALL RX1=2G RX2=2G ./arm.sh G1-all-2G-r$r G 2G 2>&1 | tail -1; pp G1-all-2G-r$r
  late && break; RATE=1500 RX1=2G RX2=2G ./arm.sh G1-rate-2G-r$r G 2G 2>&1 | tail -1; pp G1-rate-2G-r$r
  late && break; CL=LOCAL_ONE RX1=8G ./arm.sh A-lone-2G-r$r A 2G 2>&1 | tail -1; pp A-lone-2G-r$r
  if [ "$g2fail" -gt 0 ]; then late && break; CL=ALL RX1=8G RX2=8G ./arm.sh G2-all-2G-r$r G 2G 2>&1 | tail -1; pp G2-all-2G-r$r; fi
done
echo BATCH2_DONE
