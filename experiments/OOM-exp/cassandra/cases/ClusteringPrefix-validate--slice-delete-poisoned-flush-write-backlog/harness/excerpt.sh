#!/bin/bash
# U15: small excerpts of run $1 into /mydata/s4/u15/excerpts/$1 (copied to the case folder logs/<run>/). Full logs stay in /mydata/s4/u15/<run>/.
R=/mydata/s4/u15/$1; O=/mydata/s4/u15/excerpts/$1; rm -rf "$O"; mkdir -p "$O"
cp "$R/logs/driver.log" "$R/logs/settings.json" "$R/logs/conf.diff" "$R/analysis.json" "$O/" 2>/dev/null
cp "$R"/logs/data0.json "$R"/logs/poison.json "$O/" 2>/dev/null
cp "$R/hist/dump-hist.txt" "$O/" 2>/dev/null
head -45 "$R/hist/L0.txt" > "$O/L0-top.txt" 2>/dev/null; [ -f "$R/hist/L1.txt" ] && head -45 "$R/hist/L1.txt" > "$O/L1-top.txt"
# u15.t flush lines, the AssertionError with its stack (first one), OOM lines
grep -n "u15', ColumnFamily='t'\|Enqueuing flush of u15.t\|Completed flushing .*/u15/t-\|OutOfMemory\|Exception in thread Thread\[MemtablePostFlush" "$R/logs/system.log" | cut -c1-400 > "$O/system-u15.txt"
grep -n -m1 -A22 "java.lang.AssertionError: Attempted serializing" "$R/logs/system.log" > "$O/assertion-stack.txt"
grep -n -B3 -A8 "OutOfMemoryError" "$R/logs/stdout.txt" | grep -v "JVM Arguments" | cut -c1-300 | tail -30 > "$O/stdout-oom.txt"
# poll: header + every row of W (1 s), capped at 700 rows
awk 'NR==1' "$R/logs/poll.log" > "$O/poll-W.txt"; W0=$(awk '/ W start/{print int($1*1000); exit}' "$R/logs/driver.log")
awk -v w=$W0 'NR>1 && $1>=w-5000' "$R/logs/poll.log" | head -700 >> "$O/poll-W.txt"
# GC pauses in W (and the last 60 s)
grep -h "Pause" "$R"/logs/gc.log* 2>/dev/null | grep "\[gc *\]" | tail -120 > "$O/gc-pauses-last.txt"
# stall-check thread dump: headers of threads parked in the allocator + one full stack
[ -f "$R/logs/stallcheck-threads.txt" ] && python3 -I - "$R/logs/stallcheck-threads.txt" > "$O/stallcheck-parked.txt" <<'EOF'
import sys
b = open(sys.argv[1], errors='replace').read().split('\n\n')
park = [x for x in b if 'MemtableAllocator$SubAllocator.allocate' in x]
print('threads parked in MemtableAllocator$SubAllocator.allocate: %d' % len(park))
for x in park:
    print(x.strip().splitlines()[0][:160])
print('\n--- first full stack ---')
print(park[0] if park else '')
EOF
ls "$O"
