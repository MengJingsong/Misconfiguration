#!/usr/bin/env bash
# Copies excerpts of one cluster run (logs dir) to a results folder; reads only (added 2026-10-28 for the cluster re-run).
# usage: excerpt.sh <logs run dir> <results dest dir>
set -uo pipefail
SRC=${1:?src}; DST=${2:?dst}
mkdir -p "$DST"
for f in summary.txt phases.txt commands.log; do [ -f "$SRC/$f" ] && cp "$SRC/$f" "$DST/"; done
for d in "$SRC"/*/; do
  lab=$(basename "$d"); o=$DST/$lab; mkdir -p "$o"
  for f in samples.csv tpjmx.log sample-timing.txt count.out tablestats.txt; do [ -f "$d/$f" ] && cp "$d/$f" "$o/"; done
  for f in "$d"/readback-*.txt; do [ -f "$f" ] && cp "$f" "$o/"; done
  [ -f "$d/vmflags.txt" ] && tr ' ' '\n' < "$d/vmflags.txt" | grep -E 'ThreadStackSize|NativeMemoryTracking|MaxHeapSize|AlwaysPreTouch' > "$o/vmflags-excerpt.txt"
  for p in C8 C400 postshrink-C400; do [ -f "$d/$p/phase.json" ] && cp "$d/$p/phase.json" "$o/$p-phase.json"; done
  [ -f "$d/system.log" ] && grep -E 'StorageService.java:1466|CassandraDaemon.java:450|CassandraDaemon.java:744|CassandraRoleManager.java|Resized |^ERROR' "$d/system.log" > "$o/system-log-marks.txt"
done
