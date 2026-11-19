#!/usr/bin/env bash
# B18 known-answer check (design §2.5, from C6's): a JVM with the node's G1 flags holds 40 x byte[1048576], 40 x byte[1048575]
# and 1,000 HoldRegions$Marker; jcmd GC.heap_dump; hprof_scan.py must report region_arrays == 40, near_region_arrays == 40 and
# 1,000 instances of HoldRegions$Marker. Not a reading.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); O=${1:-/mydata/s4/b18-w4/logs/instrument}
mkdir -p "$O/cls"; rm -f "$O"/{ready,stop} "$O"/hold.hprof
javac -d "$O/cls" "$H/HoldRegions.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx2g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls" HoldRegions "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 100); do [ -e "$O/ready" ] && break; sleep 0.2; done
pid=$(pgrep -f "HoldRegions $O/ready")
jcmd "$pid" GC.heap_dump "$O/hold.hprof" > /dev/null
touch "$O/stop"
python3 -I "$H/hprof_scan.py" "$O/hold.hprof" > "$O/scan.json"
python3 -I -c "import json; r=json.load(open('$O/scan.json')); m=[c for c in r['classes_top'] + r['classes_named'] if c['class']=='HoldRegions\$Marker']; print('instrument check', 'ok' if r['region_arrays']==40 and r['near_region_arrays']==40 and m and m[0]['count']==1000 else 'MISMATCH', r['region_arrays'], r['near_region_arrays'], m[:1])" | tee "$O/instrument-summary.txt"
rm -f "$O/hold.hprof"
