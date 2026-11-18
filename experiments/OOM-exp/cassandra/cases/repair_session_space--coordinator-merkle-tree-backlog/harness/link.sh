#!/usr/bin/env bash
# C7 Step B.4 (on the node, instances stopped): hard-link the standard1 SSTable components into every clone dir c7/sNNN-*.
set -euo pipefail
for n in "$@"; do
  D=/mydata/s4/c7-w3/inst/$n/data/c7; S=$(ls -d $D/standard1-*)
  gen=$(ls $S/nb-*-big-Data.db | sed 's/.*nb-\([0-9]*\)-big-Data.db/\1/'); [ $(echo "$gen" | wc -l) = 1 ] || { echo "$n: more than one sstable"; exit 1; }
  k=0; for c in $D/s[0-9][0-9][0-9]-*; do ls $c/nb-* >/dev/null 2>&1 && { echo "$n: $c not empty"; exit 1; }; ln $S/nb-$gen-big-* $c/; k=$((k+1)); done
  echo "$n gen=$gen clones=$k links(Data.db)=$(stat -c %h $S/nb-$gen-big-Data.db) files=$(ls $S/nb-$gen-big-* | wc -l)"
done
