#!/usr/bin/env bash
# U9: small per-lifetime excerpts for the case folder's logs/ (full logs stay in /mydata/s4/u9-w4/runs/<label>/ on pc91).
#   excerpt.sh <label> ...  -> /mydata/s4/u9-w4/excerpts/<label>/
ROOT=/mydata/s4/u9-w4
for L in "$@"; do
  R=$ROOT/runs/$L; E=$ROOT/excerpts/$L; rm -rf "$E"; mkdir -p "$E"
  cp "$R"/{summary.txt,result.txt,run.meta,run.log,load.log,baseline.txt,gcwin.txt} "$E"/ 2>/dev/null
  cp "$R"/hprofhist.txt "$E"/ 2>/dev/null
  [ -f "$R/hprofstacks.txt" ] && awk '/^--- thread/{n++} n==1' "$R/hprofstacks.txt" > "$E/hprofstacks-first.txt"
  case $L in *-1|SHAKE) cp "$R/yaml.diff" "$E"/ 2>/dev/null;; esac
  grep -n -B2 -A8 -F "java.lang.OutOfMemoryError" "$R/stdout.log" 2>/dev/null | cut -c1-400 > "$E/stdout-oom.txt"
  [ -s "$E/stdout-oom.txt" ] || rm -f "$E/stdout-oom.txt"
  grep -E "CompactionTask|ERROR|WARN .*(Compaction|large|Guardrail)|Flushing.java:1[57]" "$R/logs/system.log" 2>/dev/null | grep -v "system[_a-z]*/\|system_" | cut -c1-600 > "$E/system-compaction.txt"
  awk '/^=== /{b=$0; next} /ks +t[12] /{print b" | "$0}' "$R/cstats.log" 2>/dev/null | tail -12 > "$E/cstats-tail.txt"
  grep -E "Humongous regions" "$R"/logs/gc.log* 2>/dev/null | tail -6 | cut -c1-200 > "$E/gc-humongous-tail.txt"
  for t in t1 t2; do [ -f "$R/listing-post-$t.txt" ] && cp "$R/listing-post-$t.txt" "$E"/; done
  [ -f "$R/histo-post.txt" ] && head -15 "$R/histo-post.txt" > "$E/histo-post-head.txt"
  du -sh "$E" | cut -f1
done
