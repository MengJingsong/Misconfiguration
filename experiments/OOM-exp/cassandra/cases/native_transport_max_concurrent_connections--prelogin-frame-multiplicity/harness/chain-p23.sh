#!/usr/bin/env bash
# U2 stage 2: waits for matrix p1b to finish, then runs priorities 2 and 3 and the optional 16 GiB-heap run (case §2.5 order).
until grep -q "matrix p1b done" /mydata/s4/u2-w1/logs/matrix-p1b.log 2>/dev/null; do sleep 10; done
exec bash /mydata/s4/u2-w1/harness/matrix.sh p23 "BT1 B partial 256 60 - on" "BT2 B partial 256 60 - on" "BT3 B partial 256 60 - on" "AU1 A partial 1120 60 - off" "AX1 A complete 1120 120 - on" "M1 M partial 1120 60 - on"
