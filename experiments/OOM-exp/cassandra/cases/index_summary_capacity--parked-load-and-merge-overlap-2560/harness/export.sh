#!/usr/bin/env bash
# R18: copy small excerpts of an arm into the case folder (run on the controller): export.sh <arm>...
C=/proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/index_summary_capacity--parked-load-and-merge-overlap-2560/logs
for a in "$@"; do d=$C/$a; mkdir -p $d
  ssh pc99 "cd /mydata/s4/r18/arms/$a && python3 /mydata/s4/r18/gen/table.py . > table.txt 2>&1; python3 /mydata/s4/r18/gen/smapspeak.py . > smapspeak.txt 2>&1; grep -E '^-X|^-D(cassandra.jmx|cassandra.config)' jvm-args.txt > jvm-args-excerpt.txt; tar cf - \$(ls summary.txt table.txt smapspeak.txt cassandra.yaml.diff dmesg-block.txt log-excerpt.txt import-P.txt import-Q.txt redistribute.txt alter.txt alter-readback.txt unit.txt t0.txt jvm-args-excerpt.txt nmt-idle.txt tablestats-postP.txt tablestats-+30.txt tablestats-+10.txt 2>/dev/null)" | tar xf - -C $d
  ssh pc99 "cd /mydata/s4/r18/arms/$a && tail -40 memstat.csv && grep -c . cstats.txt >/dev/null && tail -6 cstats.txt" > $d/memstat-cstats-tail.txt 2>&1
  ssh pc99 "python3 - /mydata/s4/r18/arms/$a/sampler.csv" > $d/sampler-excerpt.csv <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1]))); h, b = rows[0], rows[1:]
live = [r for r in b if r[1]]; tl = int(live[-1][0]) if live else 0
w = csv.writer(sys.stdout); w.writerow(h)
for i, r in enumerate(b):
    if i % 25 == 0 or int(r[0]) >= tl - 20000: w.writerow(r)
PY
done
