#!/usr/bin/env bash
# C6 known-answer check (design §2.5): a JVM with the node's G1 flags holds 40 x byte[1048576] (+ 40 x byte[1048575]);
# jcmd GC.heap_dump; hprof_scan.py must report region_arrays == 40. Not a reading.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); O=${1:-/mydata/s4/c6-w2/logs/instrument}
mkdir -p "$O/cls"; rm -f "$O"/{ready,stop} "$O"/hold.hprof
javac -d "$O/cls" "$H/HoldRegions.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx2g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls" HoldRegions "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 100); do [ -e "$O/ready" ] && break; sleep 0.2; done
pid=$(pgrep -f "HoldRegions $O/ready")
jcmd "$pid" GC.heap_dump "$O/hold.hprof" > /dev/null
touch "$O/stop"
python3 -I "$H/hprof_scan.py" "$O/hold.hprof" | tee "$O/scan.json"
python3 -c "import json,sys; r=json.load(open('$O/scan.json')); print('instrument check', 'ok' if r['region_arrays']==40 and r['near_region_arrays']==40 else 'MISMATCH')" | tee "$O/instrument-summary.txt"
rm -f "$O/hold.hprof"
