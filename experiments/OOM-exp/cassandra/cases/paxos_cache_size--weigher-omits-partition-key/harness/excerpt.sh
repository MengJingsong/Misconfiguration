#!/usr/bin/env bash
# excerpt.sh <run-id> -> prints a small excerpt of a B12 run (run on the node)
R=/mydata/s4/b12-w2/runs/$1
echo "### $1 (ms0611, aarch64). Full logs on the node: $R"
grep -v "JVM Arguments" $R/summary.txt
echo "### driver"; grep -vE "^(paxos|memtable|native|key_|counter|commitlog|cas_|read_|write_)" $R/driver.txt | head -30
echo "### first errors"; head -5 $R/errors.txt 2>/dev/null
echo "### metrics.txt (last 3)"; tail -3 $R/metrics.txt
echo "### milestone memtable/keycache lines"; grep -E "^==|MemtableOnHeap|AllMemtables|Key Cache|Heap Memory" $R/milestones.txt
echo "### OOM lines (stdout/system.log)"; grep -n "java.lang.OutOfMemoryError\|Dumping heap\|Heap dump file\|kill -9" $R/stdout.txt | grep -v "JVM Arguments" | cut -c1-200 | head -8; grep -h -A8 "ERROR.*OutOfMemory\|ERROR.*JVMStability\|Exception in thread.*OutOfMemory" $R/system.log* 2>/dev/null | cut -c1-200 | head -20
echo "### last heap_info"; tail -1 $R/heapinfo.txt | cut -c1-220
echo "### resolved flags"; grep -oE "MaxHeapSize=[0-9]+|MaxDirectMemorySize=[0-9]+|UseG1GC" $R/vm-flags.txt | sort -u
