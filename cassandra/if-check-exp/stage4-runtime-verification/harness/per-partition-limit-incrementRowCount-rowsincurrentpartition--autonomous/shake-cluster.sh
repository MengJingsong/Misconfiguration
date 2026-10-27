#!/bin/bash
# instrument check of the cluster tier on small data (not a reading): bash shake-cluster.sh
H=$(cd "$(dirname "$0")" && pwd); T=$HOME/s4-b11-q77-n; N=/dev/shm/s4-b11-q77-shake; O=$HOME/s4-b11-q77-logs/shake-cluster
ulimit -n 100000
export STAGE4_SCALE=small
python3 -I $H/cluster-run.py $T $N $O load || exit 1
python3 -I $H/cluster-run.py $T $N $O life U || exit 1
python3 -I $H/cluster-run.py $T $N $O life C || exit 1
python3 -I $H/analyze_cluster.py $O
