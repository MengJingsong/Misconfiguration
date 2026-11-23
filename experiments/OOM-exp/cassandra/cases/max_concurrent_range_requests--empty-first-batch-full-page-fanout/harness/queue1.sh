#!/usr/bin/env bash
# C10 batch: T-2G x3 then L-2G x3 (sequential lifetimes)
H=/mydata/s4/c10/harness
for k in 1 2 3; do bash $H/run-arm.sh T-2G-$k A 2G test 1:20,3:160; done
for k in 1 2 3; do bash $H/run-arm.sh L-2G-$k A 2G test 1:180; done
echo QUEUE1 DONE
