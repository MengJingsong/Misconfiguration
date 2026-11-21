#!/usr/bin/env bash
# R14: after "SEQ END P2", REP-28672M-1..2 (largest heap whose P2 point threw: CAL-CK-28G, T28 request) then P3
# (x86 replication of U5's PK condition at 2G: T-PK x3, M-PK x3 (1 x 500,015), I-PK x3). seq.sh enforces the 16:55 limit;
# $ROOT/seq.halt stops it between lifetimes.
ROOT=/mydata/s4/r14
until grep -q "SEQ END P2" $ROOT/runs/seq-P2.log; do sleep 5; done
bash $ROOT/h/seq.sh REP "REP-28672M-1 A 28672M CK 300 1800000 1500 900" "REP-28672M-2 A 28672M CK 300 1800000 1500 900"
bash $ROOT/h/seq.sh P3 "T-PK-2G-1 A 2G PK 16 500000 300 300" "T-PK-2G-2 A 2G PK 16 500000 300 300" "T-PK-2G-3 A 2G PK 16 500000 300 300" \
  "M-PK-2G-1 A 2G PK 1 500015 300 300" "M-PK-2G-2 A 2G PK 1 500015 300 300" "M-PK-2G-3 A 2G PK 1 500015 300 300" \
  "I-PK-2G-1 I 2G PK 16 500000 300 300" "I-PK-2G-2 I 2G PK 16 500000 300 300" "I-PK-2G-3 I 2G PK 16 500000 300 300"
