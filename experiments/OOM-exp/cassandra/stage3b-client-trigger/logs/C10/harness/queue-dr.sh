#!/usr/bin/env bash
# 3-b confirm C10, data-role variant: three lifetimes, role dataatk (SELECT/MODIFY on admin-made adm.t, RF 2), CL QUORUM,
# 2 GiB node 1, Q 1 for 20 s then 3 for 160 s, victim as in T-auth; dump scan after each.
H=/mydata/s4/3b-C10/harness
export ATKUSER=dataatk ATKPASS=dat-pw C10KS=adm C10CL=QUORUM LOADDIR=LOADDR
for k in 1 2 3; do bash $H/run-arm.sh DR-auth-$k A 2G test 1:20,3:160; bash $H/hprof-read.sh DR-auth-$k; done
echo QUEUE DONE
