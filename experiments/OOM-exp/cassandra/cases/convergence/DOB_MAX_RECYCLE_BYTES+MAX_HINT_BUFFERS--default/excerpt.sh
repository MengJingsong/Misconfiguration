#!/usr/bin/env bash
# copy small per-arm excerpts from the node's full logs into the repo case folder
set -u; SRC=$HOME/oom-default-run1/logs; DST=$1; shift
for a in "$@"; do s=$SRC/$a; d=$DST/logs/$a; mkdir -p "$d"
  cp "$s/summary.txt" "$d/"; cp "$s/n1-cassandra.yaml.diff" "$d/" 2>/dev/null
  cp "$s/error-count.txt" "$s/hprof.txt" "$d/" 2>/dev/null
  grep -E -- '^-Xm[sx]|MaxDirectMemorySize|NativeMemoryTracking|OnOutOfMemoryError|dob_max_recycle|MAX_HINT_BUFFERS' "$s/n1-jvm-args.txt" > "$d/n1-jvm-args-excerpt.txt"
  for w in hints dob; do [ -s "$s/stress-$w.txt" ] && tail -n 25 "$s/stress-$w.txt" | cut -c1-300 > "$d/stress-$w-tail.txt"; done
  [ -f "$s/histo-final.txt" ] && grep -E ' org.apache.cassandra.hints.HintsBuffer$| java.nio.DirectByteBuffer$' "$s/histo-final.txt" > "$d/histo-final-excerpt.txt"
  if [ "$(cat "$s/error-count.txt" 2>/dev/null)" != 0 ]; then
    grep -nE 'OutOfMemoryError|Force heap space' "$s/n1-system.log" | grep -v 'JVM Arguments' > "$d/n1-system-oom-lines.txt"
    awk '/^ERROR .*(OutOfMemory|Force heap)/{c=30} c&&c--' "$s/n1-system.log" | head -150 > "$d/n1-system-oom-excerpt.txt"
  fi
done
