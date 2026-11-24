#!/usr/bin/env bash
# 1-s loop: epoch_ms,RssAnon_kB,memory.current,oom_kill  (victim pid, its cgroup) -> <dir>/cg.csv
P=$1; CG=$2; R=$3
echo "epoch_ms,rssanon_kb,memory_current,oom_kill" > "$R/cg.csv"
while kill -0 "$P" 2>/dev/null; do
  echo "$(date +%s%3N),$(awk '/^RssAnon:/{print $2}' /proc/$P/status 2>/dev/null),$(cat $CG/memory.current 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null)" >> "$R/cg.csv"
  sleep 1
done
echo "$(date +%s%3N),GONE,$(cat $CG/memory.current 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null)" >> "$R/cg.csv"
