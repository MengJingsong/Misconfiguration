#!/usr/bin/env bash
# Copies the small excerpts of run 1 from the node's log directory into the repository (results/<stem>/run1/). usage (on the node): collect-excerpts.sh <stem> <key>
# key: blockindex | postings | maxblock | tpb. Full logs stay on the node (~/s4-b34/logs/<key>/); node stdout traces (startup logs) are not copied.
set -euo pipefail
stem=$1; key=$2
R=/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage4-runtime-verification
D=$R/results/$stem/run1; mkdir -p "$D/unit" "$D/cluster" "$D/build-patches"
L=$HOME/s4-b34/logs/$key
cp "$L"/unit/run1/*.out "$L"/unit/run1/summary.txt "$D/unit/" 2>/dev/null || true
cp "$L"/unit/run1/upstream*.log "$D/unit/" 2>/dev/null || true
for f in "$D"/unit/upstream*.log; do [ -f "$f" ] && { tail -n 30 "$f" > "$f.tail" && mv "$f.tail" "$f"; }; done
cp "$HOME"/s4-b34/logs/v-*.patch "$D/build-patches/" 2>/dev/null || true
cp "$L"/cluster/summary.txt "$D/cluster/" 2>/dev/null || true
for a in "$L"/cluster/*/; do
  n=$(basename "$a"); mkdir -p "$D/cluster/$n"
  for f in "$a"files-*.txt "$a"ledger.txt "$a"flush-lines.txt "$a"errors.txt "$a"jar.txt "$a"gauges-*.csv "$a"segments-*.txt "$a"sasi-debug.txt; do [ -f "$f" ] && cp "$f" "$D/cluster/$n/"; done
done
du -sh "$D" | tee "$D/size.txt"
