#!/usr/bin/env bash
# R21 Step A (4): reach known-answer check (design §2.5). Not a reading. Expected: reachable regions 22, only via updateF 10.
# usage: reach-check.sh [outdir]
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); O=${1:-/mydata/s4/r21/logs/reachcheck}
mkdir -p "$O/cls"; rm -f "$O"/{ready,stop} "$O"/rc.hprof
javac -d "$O/cls" "$H/reachcheck/BTree.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx1g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls" org.apache.cassandra.utils.btree.BTree "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 100); do [ -e "$O/ready" ] && break; sleep 0.2; done
pid=$(pgrep -f "org.apache.cassandra.utils.btree.BTree $O/ready" | head -1)
jcmd "$pid" GC.heap_dump "$O/rc.hprof" > /dev/null
touch "$O/stop"
t0=$(date +%s.%N)
python3 -I "$H/hprof_reach.py" "$O/rc.hprof" > "$O/reach.json"
t1=$(date +%s.%N)
python3 -I -c "
import json
r=json.load(open('$O/reach.json'))
ok = r['reachable']['regions']==22 and r['regions_only_via_updateF']==10 and r['btree_updaters_with_updateF']==1
print('reach check', 'ok' if ok else 'MISMATCH', 'reachable', r['reachable']['regions'], 'only_via_updateF', r['regions_only_via_updateF'],
      'updaters_with_updateF', r['btree_updaters_with_updateF'], 'regions_in_dump', r['regions_in_dump'], 'seconds', round($t1-$t0,2))
" | tee "$O/reach-check-summary.txt"
rm -f "$O/rc.hprof"
