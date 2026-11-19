#!/usr/bin/env bash
# B18: small excerpts of each lifetime for the case folder (full logs stay on pc75 /mydata/s4/b18-w4/logs/<label>/).
# usage (on pc75): excerpts.sh <outdir> <label> ...
W=/mydata/s4/b18-w4; O=$1; shift
mkdir -p "$O"
python3 -I $W/harness/analyze.py $W/logs "$@" > "$O/analyze.jsonl"
for l in "$@"; do
  d=$W/logs/$l; e=$O/$l; mkdir -p "$e"
  cp $d/summary.json $d/yaml.diff $e/ 2>/dev/null
  [ -f $d/memory.events ] && cp $d/memory.events $e/
  for s in $d/scan-*.json; do [ -f "$s" ] && cp "$s" $e/; done
  { head -3 $d/hotgen.csv; echo ...; tail -3 $d/hotgen.csv; } > $e/hotgen-excerpt.csv 2>/dev/null
  head -5 $d/hotgen.csv.errors > $e/hotgen-errors-head.txt 2>/dev/null
  { head -1 $d/sampler.csv; tail -8 $d/sampler.csv; } > $e/sampler-tail.csv 2>/dev/null
  grep -h "Enqueuing flush of ks.t\|Memtable-t@\|Completed flushing.*/ks/t-\|Flushed to.*/ks/t-" $d/debug.log | cut -c1-300 > $e/flush-lines.txt 2>/dev/null
  grep -n "OutOfMemoryError\|Dumping heap\|Heap dump file\|kill -9" $d/stdout.txt | grep -v "JVM Arguments\|CompileCommand" > $e/oom-lines.txt 2>/dev/null
  grep "Pause Full" $d/gc.log* 2>/dev/null | tail -5 | cut -c1-200 > $e/gc-last-full.txt
  for h in $d/hist-*-2.txt; do [ -f "$h" ] && head -16 "$h" > $e/$(basename $h .txt)-head.txt; done
  grep -h "MaxDirectMemorySize\|-Xmx\|-Xms" -o $d/jvm-cmdline.txt 2>/dev/null | head -0
  python3 -I -c "import re,sys; s=open('$d/jvm-cmdline.txt').read(); print(' '.join(re.findall(r'-X(?:mx|ms)\S+|-XX:MaxDirectMemorySize=\S+|-XX:G1\S+|-XX:\+UseG1GC|-XX:OnOutOfMemoryError=kill|-XX:\+HeapDumpOnOutOfMemoryError', s)))" > $e/jvm-flags.txt 2>/dev/null
done
du -sh "$O"
