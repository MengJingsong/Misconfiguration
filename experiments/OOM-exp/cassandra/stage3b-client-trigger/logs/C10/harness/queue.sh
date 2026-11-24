#!/usr/bin/env bash
# 3-b confirm C10: three attack lifetimes (T arm, 2 GiB node 1, Q 1 for 20 s then 3 for 160 s, as role attacker) with the victim; dump scan after each.
H=/mydata/s4/3b-C10/harness
for k in 1 2 3; do bash $H/run-arm.sh T-auth-$k A 2G test 1:20,3:160; bash $H/hprof-read.sh T-auth-$k; done
echo QUEUE DONE
