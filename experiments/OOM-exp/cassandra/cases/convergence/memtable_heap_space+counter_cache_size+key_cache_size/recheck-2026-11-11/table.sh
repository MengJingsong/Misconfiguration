#!/usr/bin/env bash
# one line per arm: peak sampled heap, final forced-GC heap, outcome, stress rates, cache K at end
cd /mydata/oom-recheck/R4/logs
for a in baseline3 validate M_alone-r1 M_alone-r2 M_alone-r3 C_alone-r1 C_alone-r2 C_alone-r3 K_alone-r1 K_alone-r2 K_alone-r3 converge-r1 converge-r2 converge-r3 ivC-r1 ivC-r2 ivC-r3 ivK-r1 ivK-r2 ivK-r3; do
  [ -d $a ] || continue; s=$a/summary.txt
  peak=$(grep '^sample' $s | grep -o 'heap *total [0-9]*K, used [0-9]*K' | sed 's/.*used //; s/K//' | sort -n | tail -1)
  fin=$(grep -E '^heap (final|idle)' $s | tail -1 | grep -o 'heap *total [0-9]*K, used [0-9]*K' | sed 's/.*used //; s/K//')
  ns=$(grep -c '^sample' $s)
  gone=$(grep -c 'node process is GONE at end' $s); err=$(grep -o 'ERROR lines in system.log: [0-9]*' $s | grep -o '[0-9]*$')
  dump=$(ls $a/node-logs/*.hprof 2>/dev/null | wc -l)
  oomt=$(cat $a/node-logs/gc.log* 2>/dev/null | grep -h 'Entering safepoint region: ReportJavaOutOfMemory' -B0 | head -1 | sed 's/^\[[0-9-]*T\([0-9:.]*\).*/kill@\1/')
  rates=$(for w in write counter read; do f=$a/stress-$w.txt; [ -f $f ] || continue; r=$(grep -m1 '^Op rate' $f | grep -o '[0-9,]* op/s' | head -1); t=$(grep -m1 '^Total operation time' $f | grep -o '[0-9:]*$'); fl=$(grep -c '^FAILURE' $f); echo -n "$w=${r:-fail}/${t:--}/F$fl "; done)
  kc=$(grep -o 'Key Cache : entries [0-9]*, size [0-9.]* [KMG]iB' $s | tail -1 | sed 's/Key Cache : entries //'); cc=$(grep -o 'Counter Cache : entries [0-9]*, size [0-9.]* [KMG]i\?B' $s | tail -1 | sed 's/Counter Cache : entries //')
  printf '%s | samples %s | peak %s K | final %s K | gone %s | dump %s | firstOOM %s | ERR %s | %s| KC %s | CC %s\n' "$a" "$ns" "$peak" "$fin" "$gone" "$dump" "$oomt" "$err" "$rates" "$kc" "$cc"
done
