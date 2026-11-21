#!/usr/bin/env bash
# R10: copy small excerpts of an arm into the case folder: export.sh <arm>...
R=/mydata/s4/r10; C=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/index_summary_capacity--parked-load-plus-compaction-overlap/logs
for a in "$@"; do s=$R/arms/$a; d=$C/$a; mkdir -p $d
  for f in summary.txt cassandra.yaml.diff dmesg-block.txt log-excerpt.txt import-P.txt import-Q.txt redistribute.txt unit.txt cstats.txt t0.txt; do [ -s $s/$f ] && cp $s/$f $d/; done
  grep -E '^-X|^-D(cassandra.jmx|cassandra.config)' $s/jvm-args.txt > $d/jvm-args-excerpt.txt 2>/dev/null
  for f in $s/nmt-idle.txt $s/nmt-+120.txt $s/tablestats-postP.txt $s/tablestats-+120.txt; do [ -s $f ] && cp $f $d/; done
  # sampler rows: every 5th row overall, plus all rows of the last 60 s of the process
  python3 - $s/sampler.csv > $d/sampler-excerpt.csv <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1]))); h, b = rows[0], rows[1:]
live = [r for r in b if r[1]]; tl = int(live[-1][0]) if live else 0
w = csv.writer(sys.stdout); w.writerow(h)
for i, r in enumerate(b):
    if i % 5 == 0 or int(r[0]) >= tl - 60000: w.writerow(r)
PY
  # smaps: last 120 s of rows
  python3 - $s/smaps.csv > $d/smaps-tail.csv <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1]))); h, b = rows[0], rows[1:]
tl = int(b[-1][0]) if b else 0
w = csv.writer(sys.stdout); w.writerow(h)
for r in b:
    if int(r[0]) >= tl - 120000: w.writerow(r)
PY
  python3 $R/gen/analyze.py $s > $d/analyze.txt 2>&1
done
