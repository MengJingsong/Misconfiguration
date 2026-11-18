#!/usr/bin/env bash
# C4: copy small excerpts of an arm into the case folder: export.sh <arm>...
R=/mydata/s4/c4-w1; C=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/index_summary_capacity--full-sampling-load-window/logs
for a in "$@"; do s=$R/arms/$a; d=$C/$a; mkdir -p $d
  for f in summary.txt cassandra.yaml.diff dmesg-block.txt log-excerpt.txt import.txt postimport.txt pool-mb.txt unit.txt; do [ -s $s/$f ] && cp $s/$f $d/; done
  grep -E '^-X|^-D(cassandra.jmx|cassandra.config)' $s/jvm-args.txt > $d/jvm-args-excerpt.txt 2>/dev/null
  t0=$(grep -oE 'import start [0-9]+' $s/summary.txt | grep -oE '[0-9]+')
  [ -n "$t0" ] && awk -F, -v a=$((t0-10000)) -v b=$((t0+30000)) 'NR==1 || ($1>=a && $1<=b)' $s/sampler.csv > $d/sampler-import-window.csv
  for f in $s/nmt-idle.txt $s/nmt-+60.txt $s/tablestats-+60.txt; do [ -s $f ] && cp $f $d/; done
  python3 $R/gen/analyze.py $s > $d/analyze.txt 2>&1
done
