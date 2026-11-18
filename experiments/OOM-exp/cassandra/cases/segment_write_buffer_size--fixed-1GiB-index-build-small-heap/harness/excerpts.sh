#!/bin/bash
# C8: copy small log excerpts of every run from the node (/mydata/s4/c8-w3/runs) into the case folder logs/.
# usage: excerpts.sh <case logs dir>
set -u
RUNS=/mydata/s4/c8-w3/runs
OUT=$1
mkdir -p "$OUT"
cp $RUNS/summary.txt "$OUT/summary.txt"
cp $RUNS/queue.log "$OUT/queue.log"
# summary recomputed with the final selfcheck.py (the first lines of summary.txt came from the first parser version, see §3 deviations)
for R in $(ls -d $RUNS/*/ | xargs -n1 basename | grep -v seed); do python3 /mydata/s4/c8-w3/h/selfcheck.py $RUNS/$R | tail -1; done > "$OUT/summary-recomputed.txt"
for R in $RUNS/*/; do
  r=$(basename $R)
  [ "$r" = seed ] && { cp $R/sstables.txt "$OUT/seed-sstables.txt"; grep -E 'Table:|SSTable count|Space used \(live\)|Number of partitions' $R/tablestats.txt > "$OUT/seed-tablestats.txt"; continue; }
  f="$OUT/$r.txt"
  {
    echo "== $r (full logs on pc96: $R)"
    cat $R/meta.txt; cat $R/notes.txt
    echo "== selfcheck"; python3 /mydata/s4/c8-w3/h/selfcheck.py $R -v
    echo "== yaml.diff"; cat $R/yaml.diff
    echo "== JVM arguments (resolved)"; grep -o 'JVM Arguments: .*' $R/system.log | head -1 | tr ',' '\n' | grep -E 'Xm[sx]|MaxDirect|ParallelGC|ConcGC|UseG1|G1HeapRegion'
    grep -E 'Global memtable on-heap|Initializing key cache|Heap size:' $R/system.log | head -3
    echo "== SAI build lines"; cat $R/system.log $R/debug.log* 2>/dev/null | grep -aE 'Starting a compaction index build|Global limit of|Submitting .* initial index builds|became queryable' | sort -u | head -60
    echo "== key cache StatusLogger (last 2)"; grep -E 'StatusLogger.*KeyCache ' $R/system.log | tail -2
    echo "== last 8 full GCs"; cat $R/gc.log* | grep -aE 'Pause Full' | sort | tail -8
    echo "== OOM lines (launch.log)"; grep -aE -A2 'OutOfMemoryError: ' $R/launch.log | head -8
    [ -f $R/hist-B0.txt ] && { echo "== hist-B0 (top 8)"; sed -n '1,11p' $R/hist-B0.txt; grep '^Total' $R/hist-B0.txt; }
    [ -f $R/hist-peak.txt ] && { echo "== hist-peak (top 15; taken on trigger in session.log)"; grep 'histogram hist-peak' $R/session.log; sed -n '1,18p' $R/hist-peak.txt; grep '^Total' $R/hist-peak.txt; }
    [ -f $R/hprofhist.txt ] && { echo "== OOM heap dump histogram (hprofhist.py, shallow)"; sed -n '1,20p' $R/hprofhist.txt; grep -E '^BB|^U4 byte\[\] +>=8' $R/hprofhist.txt; }
    [ -f $R/hprofstacks.txt ] && { echo "== OOM thread stack (from the dump)"; grep -B1 -A14 'OutOfMemoryError.<init>' $R/hprofstacks.txt | head -18;
                                   echo "== SAI builder thread stack (from the dump)"; grep -B14 -A4 'StorageAttachedIndexBuilder.build' $R/hprofstacks.txt | head -22; }
    [ -f $R/stress.log ] && { echo "== stress (every 30th interval line)"; grep -aE '^total' $R/stress.log | awk 'NR%30==1' | head -25; grep -aE 'Op rate|Total errors|END|FAILURE|Exception' $R/stress.log $R/stress.out | head -8; }
    echo "== oomtail"; python3 /mydata/s4/c8-w3/h/oomtail.py $R 2>&1 | tail -1
  } > "$f" 2>&1
done
ls -la "$OUT"
