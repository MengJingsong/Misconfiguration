#!/usr/bin/env bash
# S2 per-arm summary: summ.sh <arm dir under runs/>
d=/mydata/s2-evidence/runs/$1
o=$(cat $d/V/outcome.txt 2>/dev/null | sed 's/^[^:]*: //')
ok=$(grep FINAL $d/client/load.log | sed 's/FINAL //' | cut -c1-60)
rate=$(grep -o '(\([0-9]*\)/s)' $d/client/load.log | tr -d '(/s)' | sort -n | tail -1)
mp=$(grep MutationStage $d/V/k.log 2>/dev/null | awk '{print $3}' | sort -n | tail -1)
ob=$(awk -F'|' '{gsub(/ /,"",$3); print $3}' $d/V/out.log 2>/dev/null | sort -n | tail -1)
hu=$(grep -o 'used [0-9]*K' $d/V/heap.log | tr -dc '0-9\n' | sort -n | tail -1)
echo "$1 | $(grep -o 'V_ALIVE\|V_DEAD' $d/arm.log) | $o | client $ok peak5s=${rate}/s | MutationStage pending max=$mp | outbound pending_bytes max=$ob | heap_info used max=$((hu/1024))MiB"
mt=$(grep "Memtable data size" $d/V/k.log 2>/dev/null | awk '{print $4}' | sort -n | tail -1)
kc=$(grep "Key Cache" $d/V/k.log | tail -1 | grep -o 'size [0-9.]* [KMG]i*B' ); cc=$(grep "Counter Cache" $d/V/k.log | tail -1 | grep -o 'size [0-9.]* [KMG]i*B')
echo "   memtable data size max=$((${mt:-0}/1048576))MiB key cache $kc counter cache $cc dump: $(head -1 $d/V/dump-hist.txt 2>/dev/null) $(grep -E '^org.apache.cassandra.db.Mutation:' $d/V/dump-hist.txt 2>/dev/null)"
