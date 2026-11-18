#!/usr/bin/env bash
# C4 sampler: sampler.sh <pid> <cgroup dir> <csv> [interval s, default 0.2 (amendment 6; was 1 s)]. Runs until the pid is gone (then 3 more cgroup rows).
pid=$1; cg=$2; csv=$3; iv=${4:-0.2}
echo "epoch_ms,rss_anon_kb,vm_rss_kb,rss_file_kb,cg_current,cg_anon,cg_file,ev_max,ev_oom,ev_oom_kill" > "$csv"
row() {
  local a=",,," 
  if [ -r /proc/$pid/status ]; then a=$(awk '/^RssAnon/{x=$2}/^VmRSS/{y=$2}/^RssFile/{z=$2}END{printf "%s,%s,%s",x,y,z}' /proc/$pid/status 2>/dev/null); fi
  local c="" an="" fi="" em="" eo="" ek=""
  if [ -d "$cg" ]; then
    c=$(cat $cg/memory.current 2>/dev/null)
    read an fi < <(awk '$1=="anon"{a=$2}$1=="file"{f=$2}END{print a, f}' $cg/memory.stat 2>/dev/null)
    read em eo ek < <(awk '$1=="max"{m=$2}$1=="oom"{o=$2}$1=="oom_kill"{k=$2}END{print m, o, k}' $cg/memory.events 2>/dev/null)
  fi
  echo "$(date +%s%3N),$a,$c,$an,$fi,$em,$eo,$ek" >> "$csv"
}
while kill -0 $pid 2>/dev/null; do row; sleep $iv; done
for i in 1 2 3; do row; sleep 0.3; done
