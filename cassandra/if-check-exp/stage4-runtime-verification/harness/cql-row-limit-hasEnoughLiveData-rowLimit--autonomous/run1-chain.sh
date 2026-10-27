#!/bin/bash
# Run 1 chain (tag c74, pc12, port slot 4). Usage: bash run1-chain.sh      Logs in ~/s4-b11-c74-logs/run1/{unit,cluster}.
# Unit tier first; the cluster tier runs only if the unit tier finished (done=1). Stops at the first failed first-trigger check (exit 3 of cluster-run.py).
H=$(cd "$(dirname "$0")" && pwd); L=$HOME/s4-b11-c74-logs/run1; U=$HOME/s4-b11-c74; T=$HOME/s4-b11-c74-n; N=/dev/shm/s4-b11-c74
TL=$(cd "$H/../.." && pwd)/timing/set-A-batch-11.log
mkdir -p $L; ulimit -n 100000
echo "$(date -u +%FT%TZ) S4 c74 unit-run start" >> $TL
bash $H/unit-run.sh $U $L/unit 1000; urc=$?
echo "$(date -u +%FT%TZ) S4 c74 unit-run end" >> $TL
grep -q '^done=1' $L/unit/raw/unit.txt 2>/dev/null || { echo "unit tier did not finish; cluster tier not started"; exit 2; }
echo "$(date -u +%FT%TZ) S4 c74 cluster-run start" >> $TL
python3 -I $H/cluster-run.py $T $N $L/cluster load || { echo "load failed"; echo "$(date -u +%FT%TZ) S4 c74 cluster-run end" >> $TL; exit 1; }
python3 -I $H/cluster-run.py $T $N $L/cluster arm l1000 l10 l100 l100k lnone a100 anone s256 off10 off1000 offnone; crc=$?
python3 -I $H/analyze_cluster.py $L/cluster | tee $L/cluster/summary.txt
echo "$(date -u +%FT%TZ) S4 c74 cluster-run end" >> $TL
echo "chain done unit-rc=$urc cluster-rc=$crc"
ps -eo pid,args | grep "[j]ava.*$T" | awk '{print "LEFTOVER " $1}'
