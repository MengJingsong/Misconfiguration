#!/usr/bin/env bash
# B21 3-b confirm (pc72): heap dump scan of one lifetime as stage 2 did it (hprofhist.py, hprofowner.py, hprofstacks.py for
# the OutOfMemoryError thread), output to out/<label>/, then the .hprof is deleted.   analyze.sh <label>
ROOT=/mydata/s4/3b-B21; H=$ROOT/harness; L=$1; R=$ROOT/runs/$L; D=$ROOT/out/$L
f=$(ls "$R"/*.hprof 2>/dev/null | head -1)
[ -z "$f" ] && { echo "no hprof for $L"; exit 0; }
ls -la "$f" > "$D/hprof.ls"
python3 "$H/hprofhist.py" "$f" 30 > "$D/hprofhist.txt" 2>&1
python3 "$H/hprofowner.py" "$f" > "$D/hprofowner.txt" 2>&1
python3 "$H/hprofstacks.py" "$f" OutOfMemoryError 44 > "$D/oom-thread-stack.txt" 2>&1
python3 "$H/hprofstacks.py" "$f" > "$D/hprofstacks.txt" 2>&1; head -c 900000 "$D/hprofstacks.txt" > "$D/x" && mv "$D/x" "$D/hprofstacks.txt"
rm -f "$f"; echo "deleted $f"; ls -la "$D" | grep -c . 
