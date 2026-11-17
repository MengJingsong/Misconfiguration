#!/usr/bin/env bash
# S2 run 2 batch 6 (amendment R2-A5): equal-heap RF=2 (A topology, R1 2 GiB), 300 s load, CL=LOCAL_ONE, x3.
cd /mydata/s2r2-evidence/h; export LOAD=300 OBS=60
while pgrep -f "[b]atch5.sh" >/dev/null; do sleep 10; done
late(){ [ "$(TZ=America/New_York date +%H%M)" -ge 0135 ] && [ "$(TZ=America/New_York date +%H)" -lt 12 ]; }
for r in 1 2 3; do late && break; CL=LOCAL_ONE RX1=2G ./arm.sh Eeq-lone-2G-long-r$r A 2G 2>&1 | tail -1; done
echo BATCH6_DONE
