#!/usr/bin/env bash
# R20 (local side; R15; from U6's): copy small excerpts of finished runs into ../logs/<run>/ (full logs stay on pc82:/mydata/s4/r20/runs/).
D=$(cd "$(dirname "$0")/.." && pwd)/logs; RR=/mydata/s4/r20/runs
for r in "$@"; do
  mkdir -p $D/$r
  ssh pc82 "cd $RR/$r && python3 -I ../../harness/gctl.py . > gc-windows.txt 2>&1; grep -h GCInspector system.log* | tail -12 > gcinspector-tail.txt; head -40 completions-*.txt > completions-head.txt 2>/dev/null; tail -15 client-*.txt > client-tail.txt 2>/dev/null; grep -h -E 'ERROR|OutOfMemory' system.log* | head -20 | cut -c1-400 > system-errors.txt; true"
  for f in summary.txt driver.txt resolved.txt conf-md5.txt trigger.txt gc-windows.txt gcinspector-tail.txt completions-head.txt client-tail.txt system-errors.txt threads.txt jmx.csv dump.txt oome-thread.txt histo.txt; do
    scp -q pc82:$RR/$r/$f $D/$r/ 2>/dev/null
  done
  # R20: keep at most 20 load-response lines of summary.txt (C4 runs have ~10,000), with their count
  [ -s $D/$r/summary.txt ] && python3 -I -c "import re,sys;p=sys.argv[1];L=open(p).read().splitlines();n=0;o=[]
for l in L:
    if re.match(r'  resp \S+ t\+\S+ conn \d+ ',l):
        n+=1
        if n>20: continue
    o.append(l)
o.append('(R20 excerpt: %d load-response lines, first 20 kept)'%n);open(p,'w').write('\n'.join(o)+'\n')" $D/$r/summary.txt
  [ -s $D/$r/jmx.csv ] && { head -3 $D/$r/jmx.csv; echo ...; tail -5 $D/$r/jmx.csv; } > $D/$r/jmx-excerpt.txt; rm -f $D/$r/jmx.csv
  ssh pc82 "grep -E 'OutOfMemory|Dumping heap|Heap dump file|Executing|kill' $RR/$r/stdout.txt | head -20" > $D/$r/stdout-oom.txt
  [ -s $D/$r/stdout-oom.txt ] || rm -f $D/$r/stdout-oom.txt
done
