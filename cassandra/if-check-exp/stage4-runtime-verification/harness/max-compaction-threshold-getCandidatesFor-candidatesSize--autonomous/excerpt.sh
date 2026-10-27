#!/bin/bash
# Usage: excerpt.sh <cluster logs dir> <dest dir>   -- small text excerpts of a cluster run directory (for results/<stem>/runN/cluster/)
SRC=${1:?}; DST=${2:?}; mkdir -p "$DST"
for d in "$SRC"/run-*-N*; do
  [ -d "$d" ] || continue
  b=$(basename "$d"); mkdir -p "$DST/$b"
  for f in meta.json files-before.json tablestats-before.txt tablestats-after.txt getcompactionthreshold.txt exit.txt samples.jsonl commands.log; do [ -f "$d/$f" ] && cp "$d/$f" "$DST/$b/"; done
  grep 'standard1' "$d/system.log.copy" | grep 'Compacting (\|Compacted (' > "$DST/$b/system-log-compaction-lines.txt"
  tail -12 "$d/cassandra.yaml.used" > "$DST/$b/cassandra.yaml.tail.txt"
done
for d in "$SRC"/build-*; do
  [ -d "$d" ] || continue
  b=$(basename "$d"); mkdir -p "$DST/$b"
  for f in tablestats-phase1.txt tablestats-fixture.txt fixture-datafiles.json exit.txt; do [ -f "$d/$f" ] && cp "$d/$f" "$DST/$b/"; done
  grep -v '^[0-9:]* \$' "$d/commands.log" | grep -v '^$' | grep 'note:\|flush [0-9]*:\|phase 1\|fixture\|rounds\|settle\|FAILED\|done' > "$DST/$b/commands-summary.txt"
  ls "$d"/stress-*.txt >/dev/null 2>&1 && { grep -H 'Total errors' "$d"/stress-*.txt > "$DST/$b/stress-errors.txt"; }
done
for f in analysis.txt selfcheck.txt; do [ -f "$SRC/$f" ] && cp "$SRC/$f" "$DST/"; done
cp "$SRC"/../chain*.log "$DST/" 2>/dev/null
du -sh "$DST"
