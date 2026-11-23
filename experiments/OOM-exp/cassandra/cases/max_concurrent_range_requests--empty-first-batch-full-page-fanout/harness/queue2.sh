#!/usr/bin/env bash
# C10 batch 2: waits for queue1, then M-2G x3, I-2G x3 (Q_T = 3 from CAL-2G), then the budget search CAL-4G, CAL-8G
H=/mydata/s4/c10/harness
while ! grep -q "QUEUE1 DONE" /mydata/s4/c10/queue1.out; do sleep 10; done
for k in 1 2 3; do bash $H/run-arm.sh M-2G-$k A 2G M 1:20,3:160; done
for k in 1 2 3; do bash $H/run-arm.sh I-2G-$k I 2G test 1:20,3:160; done
bash $H/run-arm.sh CAL-4G A 4G test 4:60,6:60,8:60,12:60,16:60,24:60,32:60
bash $H/run-arm.sh CAL-8G A 8G test 8:60,12:60,16:60,24:60,32:60,48:60,64:60
echo QUEUE2 DONE
