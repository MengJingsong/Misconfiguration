#!/usr/bin/env bash
# Per-arm summary from sample.sh raw logs (fields split on '|', never summed across separators).
#   analyze.sh <run-dir>...
for R in "$@"; do
  n=$(basename "$R")
  so=$(awk -F'|' '$1 ~ /127\.0\.0\.11/ {gsub(/ /,"");
        if ($3+0>pb) pb=$3+0; if ($5+0>ov) ov=$5+0; if ($8+0>sc) sc=$8+0}
        END{printf "S->V max_pending=%.1fMiB overload=%d sent=%d", pb/1048576, ov, sc}' "$R/out.log" 2>/dev/null)
  vi=$(awk -F'|' '{gsub(/ /,""); if ($2+0>u) u=$2+0; if ($4+0>t) t=$4+0}
        END{printf "V<-S max_using=%.1fMiB throttled=%d", u/1048576, t}' "$R/vin.log" 2>/dev/null)
  hp=$(awk '/used/{gsub(/K,?/,"",$5); if ($5+0>m) m=$5+0; tot=$3} END{gsub(/K,?/,"",tot); printf "S max_used=%.0f/%.0fMiB", m/1024, tot/1024}' "$R/heap.log" 2>/dev/null)
  echo "$n | $so | $vi | $hp | $(tr '\n' ';' < "$R/outcome.txt" 2>/dev/null)"
done
