#!/usr/bin/env bash
# R1V: build small per-arm excerpts under /mydata/r1v/export/<arm>/ for copying into the case folder.
# Usage: export.sh <L_MiB> <arm> [...]   (run on the node)
R=/mydata/r1v; BUD=$1; shift
for a in "$@"; do d=$R/logs/$a; o=$R/export/$a; rm -rf "$o"; mkdir -p "$o"; [ -d "$d" ] || continue
  python3 -I $R/analyze.py "$BUD" "$d" > "$o/digest.txt" 2>&1
  cp "$d/summary.txt" "$o/" 2>/dev/null; for f in cassandra.yaml.diff startup-lines.txt dmesg-block.txt error-lines.txt oom-jvm.txt; do [ -s "$d/$f" ] && cp "$d/$f" "$o/"; done
  grep -E 'Xm[sx]|MaxDirect|AlwaysPreTouch|UseG1|NativeMemory' "$d/jvm-args.txt" > "$o/jvm-args-key.txt" 2>/dev/null
  [ -s "$d/memtable-flush-lines.txt" ] && { wc -l < "$d/memtable-flush-lines.txt" > "$o/memtable-flush-lines.txt"; tail -8 "$d/memtable-flush-lines.txt" >> "$o/memtable-flush-lines.txt"; }
  for w in preload cachefill memburst; do [ -s "$d/stress-$w.txt" ] && tail -25 "$d/stress-$w.txt" > "$o/stress-$w-tail.txt"; done
  [ -s "$d/pools.csv" ] && { head -1 "$d/pools.csv"; awk 'NR>1 && NR%15==2' "$d/pools.csv"; tail -20 "$d/pools.csv"; } > "$o/pools-excerpt.csv"
  for n in idle after-preload after-cachefill final; do [ -s "$d/nmt-$n.txt" ] && cp "$d/nmt-$n.txt" "$o/"; done
  ls "$d"/nmt-burst-*.txt >/dev/null 2>&1 && cp "$(ls "$d"/nmt-burst-*.txt | tail -1)" "$o/nmt-burst-last.txt"
done
exit 0
