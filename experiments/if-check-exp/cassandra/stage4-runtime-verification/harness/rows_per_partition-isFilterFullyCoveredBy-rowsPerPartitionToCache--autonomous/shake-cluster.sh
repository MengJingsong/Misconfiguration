#!/bin/bash
# instrument check of the cluster tier on a small data set (not a reading): bash shake-cluster.sh
H=$(cd "$(dirname "$0")" && pwd); T=$HOME/s4-b9-rp-n; N=/dev/shm/s4-b9-rp-shake; O=$HOME/s4-b9-rp-logs/shake-cluster
ulimit -n 100000
export STAGE4_NPK=400 STAGE4_NPK2=80
python3 -I $H/cluster-run.py $T $N $O load || exit 1
python3 -I $H/cluster-run.py $T $N $O arm n10 none c32 t10 || exit 1
