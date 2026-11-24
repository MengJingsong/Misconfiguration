#!/usr/bin/env bash
# 3-b confirm: paths moved to /mydata/s4/3b-C10.
# C10: read a lifetime's node-1 heap dump (histogram buckets + request-thread stacks), copy the summaries to the case
# logs, then delete the dump unless 'keep' is given.   hprof-read.sh <label> [keep]
ROOT=/mydata/s4/3b-C10; H=$ROOT/harness; L=$1; N=$ROOT/runs/$L/n1
REPO=$ROOT  # 3-b confirm: summaries go to $ROOT/logs/<label>
f=$(ls "$N"/*.hprof 2>/dev/null | head -1); [ -z "$f" ] && { echo "no hprof for $L"; exit 0; }
ls -la "$f" > "$N/hprof.ls"
taskset -c 31 python3 "$H/hprofhist.py" "$f" 30 > "$N/hprofhist.txt" 2>&1
taskset -c 31 python3 "$H/hprofstacks.py" "$f" awaitResults > "$N/stacks-await.txt" 2>&1
taskset -c 31 python3 "$H/hprofstacks.py" "$f" > "$N/stacks-all.txt" 2>&1
mkdir -p "$REPO/logs/$L"; cp "$N/hprofhist.txt" "$N/hprof.ls" "$REPO/logs/$L/"
echo "request threads in awaitResults: $(grep -c '^---' "$N/stacks-await.txt")" > "$REPO/logs/$L/stacks-summary.txt"
head -16 "$N/stacks-await.txt" >> "$REPO/logs/$L/stacks-summary.txt"
[ "${2:-}" = keep ] || { rm -f "$f"; echo "deleted $f" >> "$REPO/logs/$L/hprof.ls"; }
echo "hprof-read $L done"
