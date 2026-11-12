#!/usr/bin/env bash
# collect small per-arm excerpts into /mydata/oom-recheck/R4/excerpts/<arm>/ (copied to the repo afterwards)
cd /mydata/oom-recheck/R4/logs
O=/mydata/oom-recheck/R4/excerpts; rm -rf $O; mkdir -p $O
for a in */; do a=${a%/}; o=$O/$a; mkdir -p $o
  grep -v '^startup lines' $a/summary.txt | sed 's/\(nodetool-info [^|]*Counter Cache[^|]*\)|.*/\1/' > $o/summary.txt
  grep -oh 'Initializing [a-z]* cache with capacity of [0-9]* MiBs\|Global memtable on-heap threshold is enabled at [0-9A-Za-z]*' $a/startup-lines.txt | sort -u > $o/startup-lines.txt
  grep -E '^-X|^-XX' $a/jvm-args.txt > $o/jvm-args.txt 2>/dev/null
  cp $a/cassandra.yaml.diff $o/ 2>/dev/null
  [ -f $a/nodetool-info-final.txt ] && grep -E 'Cache' $a/nodetool-info-final.txt > $o/nodetool-info-final.txt
  [ -f $a/class-histogram-final.txt ] && head -32 $a/class-histogram-final.txt > $o/class-histogram-final-top30.txt
  for f in $a/stress-*.txt; do [ -f "$f" ] || continue; b=$(basename $f .txt)
    if grep -q '^Results:' $f; then sed -n '/^Results:/,$p' $f > $o/$b-results.txt; else { grep -m1 -B2 -A6 'FAILURE' $f; tail -3 $f; } > $o/$b-failure.txt; fi; done
  if ls $a/node-logs/*.hprof >/dev/null 2>&1; then
    ls -l $a/node-logs/*.hprof > $o/hprof-file.txt
    cat $a/node-logs/gc.log.* $a/node-logs/gc.log 2>/dev/null | grep -B8 -A3 'Entering safepoint region: HeapDumper' | grep -v '\[trace\]' > $o/gc-first-oom.txt
    cat $a/node-logs/gc.log.* $a/node-logs/gc.log 2>/dev/null | grep -B4 -A1 'Entering safepoint region: ReportJavaOutOfMemory' | grep -v '\[trace\]' > $o/gc-kill.txt
    cat $a/node-logs/gc.log.* $a/node-logs/gc.log 2>/dev/null | grep -c 'Pause Full' > $o/full-gc-count.txt
    grep -A1 '^ERROR' $a/node-logs/system.log | grep -v '^--' | sed 's/^ERROR \[[^]]*\] [^ ]* /ERROR /' | sort | uniq -c | sort -rn | head -10 > $o/system-log-errors.txt
    tail -3 $a/node-logs/system.log | cut -c1-300 > $o/system-log-tail.txt
  fi
  if ls $a/node-logs/gc.log >/dev/null 2>&1; then
    # stop-the-world share: sum of 'threads were stopped' over the last 600 s of gc.log uptime, and over the whole log
    cat $(ls -tr $a/node-logs/gc.log*) | awk -F'[][]' '/Total time for which application threads were stopped/ {u=$4; sub(/s$/,"",u); match($0,/stopped: [0-9.]+/); v=substr($0,RSTART+9,RLENGTH-9); n++; U[n]=u+0; V[n]=v+0} END {if(!n) exit; last=U[n]; tot=0; w=0; for(i=1;i<=n;i++){tot+=V[i]; if(U[i]>last-600) w+=V[i]}; printf "gc.log span %.0f s, stopped %.0f s (%.1f%%); last 600 s: stopped %.0f s (%.1f%%)\n", U[n]-U[1], tot, 100*tot/(U[n]-U[1]), w, 100*w/600}' > $o/gc-stopped-share.txt
    cat $a/node-logs/gc.log* | grep -c 'Pause Full' > $o/full-gc-count.txt
  fi
  [ -f $a/hprof-report.txt ] && cp $a/hprof-report.txt $o/
  [ -f $a/dmesg-oom.txt ] && cp $a/dmesg-oom.txt $o/
done
du -sh $O
