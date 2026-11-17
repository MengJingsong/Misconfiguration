#!/usr/bin/env bash
# S2 run 2 per-arm summary (pc96):  summ.sh <arm>
d=/mydata/s2r2-evidence/runs/$1
echo "$1 | $(grep -o '[VR][12]*_ALIVE\|[VR][12]*_DEAD' $d/arm.log | tr '\n' ' ')| $(grep -o 'args:.*' $d/arm.log | head -1 | cut -c7-80)"
ok=$(grep FINAL $d/client/load.log | sed 's/FINAL //' | cut -c1-48)
rate=$(grep -o '(\([0-9]*\)/s)' $d/client/load.log | tr -d '(/s)' | sort -n | tail -1)
first=$(grep -o '(\([0-9]*\)/s)' $d/client/load.log | head -3 | tr -d '(/s)' | tr '\n' ' ')
echo "   client $ok | peak5s=${rate}/s first15s=[$first]"
for n in V R1 R2; do [ -f $d/$n/outcome.txt ] || continue
  o=$(sed 's/^[^:]*: //' $d/$n/outcome.txt | sed 's/ | pauses=[0-9]* total_pause/ | total_pause/')
  mp=$(grep -o 'mut_pending=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  hu=$(grep -o 'heapMiB=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  mc=$(grep -o 'memcur=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  sc=$(grep -o 'swapcur=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  mt=$(grep -o 'memtable_onheap=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  hc=$(grep -o 'hints_created=[0-9]*' $d/$n/poll.log 2>/dev/null | cut -d= -f2 | sort -n | tail -1)
  dh=$(grep -E '^org.apache.cassandra.db.Mutation:' $d/$n/dump-hist.txt 2>/dev/null); sp=$(grep 'StorageProxy\$4$' $d/$n/dump-hist.txt 2>/dev/null | awk '{print $3}')
  echo "   $n: $o"
  echo "      poll: mut_pending max=$mp heap_used max=${hu}MiB memtable_onheap max=$(( ${mt:-0}/1048576 ))MiB hints_created=$hc memory.current max=$(( ${mc:-0}/1048576 ))MiB swap.current max=${sc:-?} | dump: ${dh:-none} SP\$4=${sp:-} $(head -1 $d/$n/dump-hist.txt 2>/dev/null)"
done
