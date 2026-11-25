#!/usr/bin/env bash
# (3-b confirm: pinned to 26-27 instead of 6-7) nmt.sh <pid> <cgroupdir> <outdir>: NMT summary every 2 s -> nmt.csv (via nmt.py); RssAnon/memory.current/oom_kill every 1 s -> cg.csv.
# Both loops end when the pid is gone. Pinned to cores 6-7.
P=$1 CG=$2 R=$3; H=$(cd "$(dirname "$0")" && pwd)
( echo "epoch_ms,rss_anon_kb,mem_current,oom_kill" > "$R/cg.csv"
  while kill -0 $P 2>/dev/null; do
    echo "$(date +%s%3N),$(awk '/^RssAnon:/{print $2}' /proc/$P/status 2>/dev/null),$(cat $CG/memory.current 2>/dev/null),$(awk '/^oom_kill /{print $2}' $CG/memory.events 2>/dev/null)" >> "$R/cg.csv"; sleep 1
  done; cp $CG/memory.events "$R/memory.events.final" 2>/dev/null ) &
( echo "epoch_ms,other_committed_kb,internal_committed_kb,total_committed_kb" > "$R/nmt.csv"
  while kill -0 $P 2>/dev/null; do
    t=$(date +%s%3N); taskset -c 26-27 jcmd $P VM.native_memory summary 2>/dev/null | python3 "$H/nmt.py" "$t" >> "$R/nmt.csv"
    sleep 2
  done ) &
wait
