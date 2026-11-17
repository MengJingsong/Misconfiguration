#!/usr/bin/env bash
# Known-answer check of the histogram reading (run on pc91 before run 1): a JVM with the node's G1 flags
# (-XX:+UseG1GC -XX:G1HeapRegionSize=16m, -Xmx2g) in a systemd-run scope allocates K live byte[1048576];
# the second of two class histograms after minus before must be K x 1,048,592 B (within 64 KiB).
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); O=${1:-/mydata/s4/slabrc-logs/run1/instrument}; K=${K:-40}
mkdir -p "$O/cls"; rm -f "$O"/{go,done,stop}
javac -d "$O/cls" "$H/HoldBytes.java"
systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 java -Xmx2g -XX:+UseG1GC -XX:G1HeapRegionSize=16m -cp "$O/cls" HoldBytes $K "$O/go" "$O/done" "$O/stop" > "$O/java.out" 2>&1 &
sleep 3; pid=$(pgrep -f "HoldBytes $K $O/go")
bb() { jcmd $pid GC.class_histogram | awk '$4=="[B"{print $3}'; }
bb >/dev/null; b0=$(bb); touch "$O/go"; until [ -e "$O/done" ]; do sleep 0.2; done
bb >/dev/null; b1=$(bb); touch "$O/stop"; wait
d=$((b1-b0)); want=$((K*1048592))
echo "K=$K before=$b0 after=$b1 delta=$d want=$want diff=$((d-want)) $( [ ${d#-} -ge 0 ] && [ $(( (d-want) < 0 ? want-d : d-want )) -le 65536 ] && echo ok || echo MISMATCH)" | tee "$O/instrument-summary.txt"
