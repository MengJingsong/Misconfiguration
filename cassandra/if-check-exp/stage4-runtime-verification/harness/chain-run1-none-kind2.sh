#!/bin/bash
# Run 1 of the three none-type cases (unit tier), one after another, on one node. Usage: bash chain-run1.sh <tree> <out-root>
# For each case: plain JVM (instrument), Byteman JVM (counts), then analyze.py. Stops on the first failed step.
set -u
TREE=${1:?}; ROOT=${2:?}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT"
for stem in no_constraint-iscolumnrange-clustering_restrictions no_constraint-doesaggregation-aggregatefactories no_constraint-needfiltering-restriction_count; do
  d=$HERE/${stem}--autonomous; o=$ROOT/$stem
  echo "[$(date +%FT%T)] === $stem (load: $(cut -d' ' -f1-3 /proc/loadavg))" | tee -a "$ROOT/chain.log"
  bash $d/unit-run.sh $TREE $d $o/plain 0 || { echo "plain run failed for $stem" | tee -a "$ROOT/chain.log"; exit 1; }
  bash $d/unit-run.sh $TREE $d $o/bm 1 || { echo "byteman run failed for $stem" | tee -a "$ROOT/chain.log"; exit 1; }
  python3 $d/analyze.py $o/plain/raw $o/bm/raw > $o/analyze.out 2>&1
  echo "[$(date +%FT%T)] analyze done: $(grep -c '^PASS' $o/analyze.out) PASS, $(grep -c '^FAIL' $o/analyze.out) FAIL" | tee -a "$ROOT/chain.log"
done
echo "[$(date +%FT%T)] chain finished" | tee -a "$ROOT/chain.log"
