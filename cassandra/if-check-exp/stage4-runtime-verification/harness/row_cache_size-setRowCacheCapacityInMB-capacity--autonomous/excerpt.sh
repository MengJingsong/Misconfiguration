#!/usr/bin/env bash
# usage: excerpt.sh <raw cluster log dir> <excerpt dir>
# Cluster re-run (2026-10-27): copies small text excerpts of a cluster run's raw logs into the repository, in the layout of
# results/<stem>/run1/cluster/ plus the ledger one-shots and the agent lines. Reads only; never edits a raw file.
set -uo pipefail
S=${1:?raw}; D=${2:?out}
mkdir -p "$D"
for f in commands.log summary.txt testscript.txt; do [ -f "$S/$f" ] && cp "$S/$f" "$D/"; done
for r in write BASE R512 R128 R64 R32 Y64 R8 R4 R2 Y4 RT; do
  s=$S/$r; [ -d "$s" ] || continue
  d=$D/$r; mkdir -p "$d"
  for f in yaml-tail.txt rss.txt samples.csv schema.txt error-count.txt neg.txt ledger-start.txt ledger-end.txt ledger-beforeset.txt ledger-afterset.txt ledger-aftermisses.txt; do
    [ -f "$s/$f" ] && cp "$s/$f" "$d/"
  done
  for f in "$s"/info-*.txt; do [ -f "$f" ] && grep -E 'Cache' "$f" > "$d/$(basename "$f" .txt)-caches.txt"; done
  for f in "$s"/stress-*.txt; do [ -f "$f" ] && sed -n '/^Results:/,$p' "$f" > "$d/$(basename "$f" .txt)-results.txt"; done
  for f in "$s"/nmt-*.txt; do [ -f "$f" ] && grep -E '^Total:|Java Heap|Internal \(|Other \(' "$f" > "$d/$(basename "$f" .txt)-excerpt.txt"; done
  [ -f "$s/tablestats.txt" ] && grep -E 'SSTable count|Space used \(live\)|Space used \(total\)|Number of partitions' "$s/tablestats.txt" > "$d/tablestats-excerpt.txt"
  [ -f "$s/compactionhistory.txt" ] && { head -2 "$s/compactionhistory.txt"; grep ' keyspace1 ' "$s/compactionhistory.txt"; } > "$d/compactionhistory-keyspace1.txt"
  if [ -f "$s/node/system.log" ]; then
    { grep -m1 -o 'JVM Arguments: .*' "$s/node/system.log" | tr ',' '\n' | grep -E -- '-Xm[sx]|NativeMemoryTracking|-javaagent'
      grep -E 'Initializing row cache with capacity|OHC using|Preloaded [0-9]+ prepared' "$s/node/system.log"; } > "$d/node-log-excerpt.txt"
  fi
  [ -f "$s/node/node.out" ] && grep -E 'RCSLEDGER|TypeException|Rule\.execute called for|org\.jboss\.byteman' "$s/node/node.out" > "$d/node-out-agent-lines.txt"
done
echo "excerpts: $(find "$D" -type f | wc -l | tr -d ' ') files, $(du -sk "$D" | cut -f1) KiB"
