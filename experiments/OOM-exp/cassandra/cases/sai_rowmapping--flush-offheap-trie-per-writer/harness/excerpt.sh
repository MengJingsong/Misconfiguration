#!/bin/bash
# U13: small per-run excerpt (analysis with direct steps, driver log, first OOM with 45 lines, resolved flags) to stdout.
# usage: bash excerpt.sh <run label>
R=/mydata/s4/u13/$1; H=$(dirname "$(readlink -f "$0")")
echo "### $1 (full logs: ms0617:$R/logs, NMT: $R/nmt)"
echo "--- analyze.py"; python3 -I "$H/analyze.py" "$R" steps | grep -v '^   '
echo "--- driver.log"; grep -v 'Row\[u13' "$R/logs/driver.log" | grep -v '^\(Mem\|Swap\|Filesystem\|/dev\| \)'
echo "--- vmflags"; grep -o 'MaxDirectMemorySize=[0-9]*\|MaxHeapSize=[0-9]*' "$R/logs/vmflags.txt" | tr '\n' ' '; echo
L=$(grep -n 'java.lang.OutOfMemoryError' "$R/logs/system.log" 2>/dev/null | grep -v 'JVM Arguments' | head -1 | cut -d: -f1)
if [ -n "$L" ]; then echo "--- first OOM (system.log from line $((L-1)))"; sed -n "$((L-1)),$((L+44))p" "$R/logs/system.log" | cut -c1-220; fi
