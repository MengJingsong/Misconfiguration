#!/usr/bin/env bash
# usage: excerpt.sh <raw run dir> <excerpt dir>      (cluster re-run 2026-10-28; reads only, copies small excerpts)
# Copies summary.txt and commands.log, and per S: the startup line, rep.log, the cqlsh outputs, the histogram rows of the repair
# classes and Guava entries plus Total, the analyser outputs ret-*.txt (whole), the dump sizes and the first 3 lines of the log segment.
set -uo pipefail
SRC=${1:?raw}; DST=${2:?excerpt}; mkdir -p "$DST"
cp "$SRC/summary.txt" "$SRC/commands.log" "$DST/"
for d in "$SRC"/S*; do
  s=$(basename "$d"); o=$DST/$s; mkdir -p "$o"
  grep -h 'Storing repair state for' "$d/n1/system.log" > "$o/startline.txt"
  cp "$d/rep.log" "$d"/cql-*.txt "$o/" 2>/dev/null
  for h in "$d"/hist-*.txt; do grep -E 'repair\.state|RepairOption|RepairCoordinator|LocalCache\$Strong|^Total' "$h" > "$o/$(basename "$h" .txt)-excerpt.txt"; done
  cp "$d"/ret-*.txt "$o/" 2>/dev/null
  ls -l "$d"/*.hprof 2>/dev/null | awk '{print $5, $NF}' > "$o/dump-sizes.txt"
  head -3 "$d/system-segment.log" > "$o/system-segment-first3.txt"
done
