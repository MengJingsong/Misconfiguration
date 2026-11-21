#!/usr/bin/env bash
# R16 known-answer check (design §2.5 Step A; B18's check extended): a JVM with the node's G1 flags holds 40 x byte[1048576],
# 40 x byte[1048575], 1,000 HoldRegions$Marker and one HoldRegions$FieldProbe; jcmd GC.heap_dump; hprof_scan.py must report
# region_arrays == 40, near_region_arrays == 40, 1,000 HoldRegions$Marker, and (with --decode) the probe's field values exactly:
# lb 0x0123456789ABCDEF (inherited long), ib 4242 (inherited int), ref -> AtomicLong 31337, ai -> AtomicInteger 77,
# ph -> enum ordinal 2, own -5. Not a reading.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); O=${1:-/mydata/s4/r16/logs/instrument}
mkdir -p "$O/cls"; rm -f "$O"/{ready,stop} "$O"/hold.hprof
javac -d "$O/cls" "$H/HoldRegions.java"
( setsid nohup systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx2g -XX:+UseG1GC -XX:G1HeapRegionSize=16m \
    -cp "$O/cls" HoldRegions "$O/ready" "$O/stop" < /dev/null > "$O/java.out" 2>&1 & )
for i in $(seq 1 100); do [ -e "$O/ready" ] && break; sleep 0.2; done
pid=$(pgrep -f "HoldRegions $O/ready" | head -1)
jcmd "$pid" GC.heap_dump "$O/hold.hprof" > /dev/null
touch "$O/stop"
python3 -I "$H/hprof_scan.py" "$O/hold.hprof" > "$O/scan.json"
python3 -I "$H/hprof_scan.py" --decode 'HoldRegions$FieldProbe,HoldRegions$ProbeBase,HoldRegions$Phase' "$O/hold.hprof" > "$O/scan-decode.json"
python3 -I -c "
import json
r=json.load(open('$O/scan.json')); d=json.load(open('$O/scan-decode.json'))
m=[c for c in r['classes_top'] + r['classes_named'] if c['class']=='HoldRegions\$Marker']
fp=d['decoded'].get('HoldRegions\$FieldProbe', [])
want={'lb': 0x0123456789ABCDEF, 'ib': 4242, 'ref': 31337, 'ai': 77, 'ph': {'enum': 'HoldRegions\$Phase', 'ordinal': 2}, 'own': -5}
okf = len(fp)==1 and all(fp[0].get(k)==v for k,v in want.items())
ok = r['region_arrays']==40 and r['near_region_arrays']==40 and m and m[0]['count']==1000 and okf
print('instrument check', 'ok' if ok else 'MISMATCH', r['region_arrays'], r['near_region_arrays'], m[:1], fp)
print('cassandra keys present:', 'pool' in r, 'allocators' in r, 'writer_traces' in r)
" | tee "$O/instrument-summary.txt"
rm -f "$O/hold.hprof"
