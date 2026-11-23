#!/usr/bin/env bash
# C10 batch 3 (optional arms): waits for queue2, then I4-2G (cap 4) and CAL-auto (auto heap)
H=/mydata/s4/c10/harness
while ! grep -q "QUEUE2 DONE" /mydata/s4/c10/queue2.out; do sleep 10; done
bash $H/run-arm.sh I4-2G I4 2G test 1:20,3:160
bash $H/run-arm.sh CAL-auto A auto test 16:60,32:60,48:60,64:60,96:60,120:60
echo QUEUE3 DONE
