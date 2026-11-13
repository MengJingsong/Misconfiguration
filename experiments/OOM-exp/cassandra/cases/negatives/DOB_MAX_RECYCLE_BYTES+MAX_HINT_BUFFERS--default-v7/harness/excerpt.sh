#!/usr/bin/env bash
# R6-V: copy small per-arm excerpts from /mydata/r6v/logs into a staging dir (then copied to the repo's logs/)
set -u; SRC=/mydata/r6v/logs; DST=$1; shift
for a in "$@"; do s=$SRC/$a; d=$DST/$a; mkdir -p "$d"
  cp "$s/summary.txt" "$s/error-count.txt" "$s/hprof.txt" "$d/" 2>/dev/null
  grep -E -- '^-Xm[sx]|MaxDirectMemorySize|NativeMemoryTracking|OnOutOfMemoryError|dob_max_recycle|MAX_HINT_BUFFERS' "$s/n1-jvm-args.txt" > "$d/n1-jvm-args-excerpt.txt"
  for w in H F D R; do [ -s "$s/stress-$w.txt" ] && grep -E '^total,' "$s/stress-$w.txt" | tail -n 3 | cut -c1-200 > "$d/stress-$w-tail.txt"; done
  [ -f "$s/histo-final.txt" ] && grep -E ' org.apache.cassandra.hints.HintsBuffer$| java.nio.DirectByteBuffer$' "$s/histo-final.txt" > "$d/histo-final-excerpt.txt"
  [ -f "$s/hprof-analysis.txt" ] && sed -n '/== java.nio.DirectByteBuffer ==/,$p' "$s/hprof-analysis.txt" | cut -c1-200 > "$d/hprof-direct-holders.txt"
  if [ "$(cat "$s/error-count.txt" 2>/dev/null)" != 0 ] || grep -q OutOfMemory "$s/oom-jvm.txt" 2>/dev/null; then
    grep -nE 'OutOfMemoryError|Force heap' "$s/n1-system.log" | grep -v 'JVM Arguments' | cut -c1-250 > "$d/n1-system-oom-lines.txt"
    awk '/^ERROR .*(OutOfMemory|Force heap)/{c=40} c&&c--' "$s/n1-system.log" | head -120 | cut -c1-250 > "$d/n1-system-oom-excerpt.txt"
    grep -E 'ReportJavaOutOfMemory|Pause Full' "$s"/n1-gc.log* 2>/dev/null | tail -6 | cut -c1-250 > "$d/n1-gc-tail.txt"
  fi
done
cp "$SRC/S_conv_r1/n1-cassandra.yaml.diff" "$DST/n1-cassandra.yaml.diff"
