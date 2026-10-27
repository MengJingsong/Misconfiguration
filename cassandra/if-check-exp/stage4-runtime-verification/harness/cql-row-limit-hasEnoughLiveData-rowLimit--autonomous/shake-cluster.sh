#!/bin/bash
# instrument check of the cluster tier on small data (not a reading): bash shake-cluster.sh
H=$(cd "$(dirname "$0")" && pwd); T=$HOME/s4-b11-c74-n; N=/dev/shm/s4-b11-c74-shake; O=$HOME/s4-b11-c74-logs/shake-cluster
ulimit -n 100000
export STAGE4_NPK=40 STAGE4_READS=400 STAGE4_IDLE=10
python3 -I $H/cluster-run.py $T $N $O load || exit 1
python3 -I $H/cluster-run.py $T $N $O arm l1000 l10 a100 s256 off10 || exit 1
python3 -I $H/analyze_cluster.py $O 400 40
