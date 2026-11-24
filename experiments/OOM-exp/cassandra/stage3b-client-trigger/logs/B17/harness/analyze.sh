#!/usr/bin/env bash
# B17 3-b confirm (pc75): heap dump scan of one lifetime as stage 2 did it (hprofhist.py with the B17 buckets;
# hprofstacks.py for the threads in the replica read / ResultSet phase, whole stacks), output to out/<label>/, then the
# .hprof is deleted.   analyze.sh <label>
ROOT=/mydata/s4/3b-B17; H=$ROOT/harness; L=$1; R=$ROOT/runs/$L; D=$ROOT/out/$L
f=$(ls "$R"/*.hprof 2>/dev/null | head -1)
[ -z "$f" ] && { echo "no hprof for $L"; exit 0; }
mkdir -p "$D"; ls -la "$f" > "$D/hprof.ls"
python3 "$H/hprofhist.py" "$f" 30 > "$D/hprofhist.txt" 2>&1
python3 "$H/hprofstacks.py" "$f" LocalDataResponse 40 > "$D/hprofstacks-replica.txt" 2>&1
python3 "$H/hprofstacks.py" "$f" processPartition 40 > "$D/hprofstacks-resultset.txt" 2>&1
python3 "$H/hprofstacks.py" "$f" expandToFit 40 > "$D/hprofstacks-expand.txt" 2>&1
for x in "$D"/hprofstacks-*.txt; do [ -s "$x" ] || rm -f "$x"; done
rm -f "$f"; echo "deleted $f"
