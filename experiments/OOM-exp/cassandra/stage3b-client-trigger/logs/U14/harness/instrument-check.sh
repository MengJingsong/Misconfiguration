#!/usr/bin/env bash
# U14 known-answer check (design §2.5): a JVM (node's G1 flags) holds 1,000 marker Strings of 222 chars + 500 long[330];
# jcmd GC.heap_dump; HprofScan must report >= 1,000 marker byte[] and exactly 500 long[330]. Not a reading.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); W=/mydata/s4/3b-U14; O=${1:-$W/logs/instrument}
mkdir -p "$O/cls" "$W/jmxcls"; rm -f "$O"/{ready,stop} "$O"/hold.hprof
javac -d "$O/cls" "$H/Hold.java"
javac -d "$W/jmxcls" "$H/HprofScan.java" "$H/Jmx.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx2g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls" Hold "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 100); do [ -e "$O/ready" ] && break; sleep 0.2; done
pid=$(pgrep -f "Hold $O/ready" | head -1)
jcmd "$pid" GC.heap_dump "$O/hold.hprof" > /dev/null
touch "$O/stop"
/usr/bin/time -f '%e s %M KB' java -Xmx1g -cp "$W/jmxcls" HprofScan "$O/hold.hprof" > "$O/scan.json"
python3 -c "import json; r=json.load(open('$O/scan.json')); ok=r['marker_byte_arrays']>=1000 and r['long330_arrays']==500; print('instrument check', 'ok' if ok else 'MISMATCH', r['marker_byte_arrays'], r['long330_arrays'], r['total_shallow_bytes'])" | tee "$O/instrument-summary.txt"
rm -f "$O/hold.hprof"
