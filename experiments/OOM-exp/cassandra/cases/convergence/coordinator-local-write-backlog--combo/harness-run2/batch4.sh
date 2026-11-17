#!/usr/bin/env bash
# S2 run 2 batch 4 (amendment R2-A3): G2 matched control, client capped at 1 500 writes/s, x3. Starts after batch 3.
cd /mydata/s2r2-evidence/h; export LOAD=90 OBS=60
while pgrep -f "[b]atch3.sh" >/dev/null; do sleep 10; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
for r in 1 2 3; do late && break; RATE=1500 RX1=8G RX2=8G ./arm.sh G2-rate-2G-r$r G 2G 2>&1 | tail -1; done
echo BATCH4_DONE
