#!/usr/bin/env bash
# Runs the B3b values one after another (fresh node, wiped data per K), then the analyzer.
WORK=/mydata/jingsong-cass-s4/o04
RUN=${1:?run}
mkdir -p $WORK/logs/$RUN
for K in 100 100000 1000000; do
  bash $WORK/harness/cluster-run.sh $RUN $K || { echo "K=$K failed" >> $WORK/logs/$RUN/cluster-all.txt; break; }
  echo "K=$K ok $(date -u +%FT%TZ)" >> $WORK/logs/$RUN/cluster-all.txt
done
python3 $WORK/harness/cluster-analyze.py $WORK/logs/$RUN > $WORK/logs/$RUN/cluster-analysis.txt 2>&1
echo "all done $(date -u +%FT%TZ)" >> $WORK/logs/$RUN/cluster-all.txt
