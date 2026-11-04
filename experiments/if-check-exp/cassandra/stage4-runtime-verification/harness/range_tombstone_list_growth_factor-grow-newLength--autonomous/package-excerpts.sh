#!/usr/bin/env bash
# package.sh <t> <stem> : small text excerpts of ~/stage4-logs/rtl/<t>/run1 into results/<stem>/run1/ (full logs stay on the node)
set -euo pipefail
t=$1; stem=$2
R=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/results/$stem/run1
S=$HOME/stage4-logs/rtl/$t/run1/cluster
mkdir -p $R/cluster
cp $S/cells.jsonl $S/readings.csv $S/session.log $S/harness.md5 $R/cluster/ 2>/dev/null || true
for y in $S/cassandra-*.yaml; do tail -n 20 "$y" > $R/cluster/$(basename "$y" .yaml)-tail.yaml; done
for d in $S/*/; do
  c=$(basename "$d"); [ -f "$d/series.csv" ] || continue
  mkdir -p $R/cluster/$c
  cp "$d/series.csv" $R/cluster/$c/
  for h in "$d"/histo-*.txt; do
    grep -E 'ClusteringBound|RangeTombstoneList$|  \[J |  \[I |  \[B |^Total' "$h" | head -12 > $R/cluster/$c/$(basename "$h")
  done
  { head -n 3 "$d/growth-trace.txt"; echo ...; tail -n 3 "$d/growth-trace.txt"; echo "lines: $(wc -l < "$d/growth-trace.txt")"; } > $R/cluster/$c/growth-trace-excerpt.txt
  awk 'NR==1 || NR%40==0' "$d/heap.txt" > $R/cluster/$c/heap-every40th.txt
done
for s in $S/system-*.log; do { grep -E '^(ERROR|WARN)' "$s" | head -5; echo "lines: $(wc -l < "$s"); ERROR lines: $(grep -c '^ERROR' "$s"); flush lines: $(grep -c 'Flushing largest\|Enqueuing flush' "$s")"; } > $R/cluster/$(basename "$s" .log)-summary.txt; done
[ -f $S/analysis.txt ] && cp $S/analysis.txt $R/cluster/
[ -f $S/selfcheck.txt ] && cp $S/selfcheck.txt $R/cluster/
du -sh $R
