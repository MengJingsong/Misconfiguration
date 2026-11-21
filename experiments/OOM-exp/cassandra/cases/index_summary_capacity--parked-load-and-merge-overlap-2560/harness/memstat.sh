#!/usr/bin/env bash
# R18 memstat.sh <pid> <cgroup dir> <csv> [interval s, default 1]: the ceiling terms of design §2.6 every interval from the
# scope's memory.stat (bytes): memory.current, anon, file, file_mapped, kernel_stack, pagetables, slab, sock; until the pid
# is gone, then 3 more rows.
pid=$1; cg=$2; csv=$3; iv=${4:-1}
echo "epoch_ms,cg_current,anon,file,file_mapped,kernel_stack,pagetables,slab,sock" > "$csv"
row() { [ -d "$cg" ] || { echo "$(date +%s%3N),,,,,,,," >> "$csv"; return; }
  echo "$(date +%s%3N),$(cat $cg/memory.current 2>/dev/null),$(awk '$1=="anon"{a=$2}$1=="file"{f=$2}$1=="file_mapped"{m=$2}$1=="kernel_stack"{k=$2}$1=="pagetables"{p=$2}$1=="slab"{s=$2}$1=="sock"{o=$2}END{printf "%s,%s,%s,%s,%s,%s,%s",a,f,m,k,p,s,o}' $cg/memory.stat 2>/dev/null)" >> "$csv"; }
while kill -0 $pid 2>/dev/null; do row; sleep $iv; done
for i in 1 2 3; do row; sleep 0.3; done
