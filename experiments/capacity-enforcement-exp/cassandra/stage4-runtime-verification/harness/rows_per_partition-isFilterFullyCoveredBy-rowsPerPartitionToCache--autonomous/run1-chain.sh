#!/bin/bash
# Run 1 chain (tag rp, pc07, port slot 2). Usage: bash run1-chain.sh      Logs in ~/s4-b9-rp-logs/run1/{unit,cluster}.
# Unit tier first; the cluster tier runs only if the unit tier finished (done=1). Stops at the first failed first-trigger check (exit 3 of cluster-run.py).
H=$(cd "$(dirname "$0")" && pwd); L=$HOME/s4-b9-rp-logs/run1; U=$HOME/s4-b9-rp; T=$HOME/s4-b9-rp-n; N=/dev/shm/s4-b9-rp
TL=$(cd "$H/../.." && pwd)/timing/set-A-batch-9.log
mkdir -p $L; ulimit -n 100000
echo "$(date -u +%FT%TZ) S4 rp unit-run start" >> $TL
bash $H/unit-run.sh $U $L/unit 1000; urc=$?
echo "$(date -u +%FT%TZ) S4 rp unit-run end" >> $TL
grep -q '^done=1' $L/unit/raw/unit.txt 2>/dev/null || { echo "unit tier did not finish; cluster tier not started"; exit 2; }
echo "$(date -u +%FT%TZ) S4 rp cluster-run start" >> $TL
python3 -I $H/cluster-run.py $T $N $L/cluster load || { echo "load failed"; echo "$(date -u +%FT%TZ) S4 rp cluster-run end" >> $TL; exit 1; }
python3 -I $H/cluster-run.py $T $N $L/cluster arm n10 n1 n100 nall t10 none c32; crc=$?
python3 -I $H/analyze_cluster.py $L/cluster | tee $L/cluster/summary.txt
echo "$(date -u +%FT%TZ) S4 rp cluster-run end" >> $TL
echo "chain done unit-rc=$urc cluster-rc=$crc"
ps -eo pid,args | grep "[j]ava.*$T" | awk '{print "LEFTOVER " $1}'
