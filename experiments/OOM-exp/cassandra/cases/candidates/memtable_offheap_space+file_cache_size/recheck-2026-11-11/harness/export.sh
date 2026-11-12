#!/usr/bin/env bash
# Copy small excerpts of each arm into the repo case folder: export.sh <dest-dir> <arm>...
dest=$1; shift; R=/mydata/oom-recheck/R1
for a in "$@"; do s=$R/logs/$a; d=$dest/$a; [ -d "$s" ] || s=$R/logs-validation/$a; mkdir -p "$d"
  cp "$s"/summary.txt "$s"/cassandra.yaml.diff "$s"/jvm-args.txt "$s"/startup-lines.txt "$d"/ 2>/dev/null
  for f in memtable-flush-lines.txt dmesg-block.txt error-lines.txt bufferpool-lines.txt nmt-idle.txt nmt-after-cachefill.txt nmt-final.txt; do [ -s "$s/$f" ] && cp "$s/$f" "$d/"; done
  last=$(ls "$s"/nmt-burst-*.txt 2>/dev/null | tail -1); [ -n "$last" ] && cp "$last" "$d/nmt-burst-last.txt"
  for w in preload cachefill memburst; do [ -s "$s/stress-$w.txt" ] && tail -22 "$s/stress-$w.txt" > "$d/stress-$w-tail.txt"; done
  [ -s "$s/pools.csv" ] && { n=$(wc -l < "$s/pools.csv"); awk -v n="$n" 'NR==1 || NR%10==0 || NR>n-30' "$s/pools.csv" > "$d/pools-excerpt.csv"; }
  python3 -I $R/tools/analyze.py "$s" > "$d/digest.txt"
done
