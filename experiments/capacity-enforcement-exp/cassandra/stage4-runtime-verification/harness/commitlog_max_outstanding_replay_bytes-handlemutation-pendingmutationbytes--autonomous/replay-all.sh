#!/usr/bin/env bash
H=/mydata/jingsong-cass-s4/o32/harness
bash $H/cluster-run.sh replay b16m 16777216 100000000
bash $H/cluster-run.sh replay b64m 67108864 100000000
bash $H/cluster-run.sh replay b256m 268435456 100000000
bash $H/cluster-run.sh replay b4g 4294967296 100000000
bash $H/cluster-run.sh replay c16 4294967296 16
echo ALLDONE > /mydata/jingsong-cass-s4/o32/cluster/ALLDONE
