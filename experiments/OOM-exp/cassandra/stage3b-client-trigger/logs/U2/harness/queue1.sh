#!/usr/bin/env bash
# U2 3-b: control C-2 (50 stalled frames held 60 s, ARM=control), then attack T-B-1 (budget B, k_max 256, as stage 2 BT).
cd /mydata/s4/3b-U2
[ -f STOP ] || ARM=control bash harness/run3b.sh C-2 B partial 50 60 - on > logs/C-2.console 2>&1
[ -f STOP ] || bash harness/run3b.sh T-B-1 B partial 256 60 - on > logs/T-B-1.console 2>&1
echo "queue1 done $(date)" >> logs/queue1.log
