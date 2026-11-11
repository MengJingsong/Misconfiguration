#!/bin/bash
# instrument check of the cluster tier on a small data set (not a reading): bash shake-cluster.sh
H=$(cd "$(dirname "$0")" && pwd); T=$HOME/s4-b11-p75-n; N=/dev/shm/s4-b11-p75-shake; O=$HOME/s4-b11-p75-logs/shake-cluster
ulimit -n 100000
export STAGE4_NPK=400 STAGE4_NPK2=80
python3 -I $H/cluster-run.py $T $N $O load || exit 1
python3 -I $H/cluster-run.py $T $N $O arm n5 n50 none t5 || exit 1
