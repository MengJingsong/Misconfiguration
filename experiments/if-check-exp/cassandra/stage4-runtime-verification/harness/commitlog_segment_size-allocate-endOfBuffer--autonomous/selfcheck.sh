#!/bin/bash
# Independent re-derivation (awk / grep / sort, no shared code with analyze_*.py) of the readings the conclusion cites.
# Usage: bash selfcheck.sh <runroot>   (runroot holds unit/<arm>/ and cluster/<arm>/)
R=${1:?}
echo "== unit: per arm, from seg.csv and the raw test log"
for d in $R/unit/*/; do a=$(basename $d)
  S=$(grep -m1 '^INFO' $d/seg.summary | tr ' ' '\n' | sed -n 's/^S=//p')
  awk -F, -v S=$S -v A=$a 'NR>1{ if($2!=S)bc++; if($3>=$2)bm++; if($6=="false"&&($5!=$2+1||$4>=$2))br++; if($7>S)ov++; n++; if($7>mx)mx=$7; if($3>me)me=$3 }
    END{printf "%s S=%d segs=%d cap!=S:%d maxEnd>=cap:%d retiredBad:%d files>S:%d maxFile=%d maxEnd=%d\n",A,S,n,bc,bm,br,ov,mx,me}' $d/seg.csv
  printf '   junit: %s | conf: %s | probes: ' "$(grep -o 'tests="[0-9]*" .*failures="[0-9]*"' $d/TEST-*.xml | head -1 | cut -c1-60)" "$(grep -ho 'commitlog_segment_size[^,;]*' $d/testlogs/*/* 2>/dev/null | sort -u | head -1)"
  grep -c '^PROBE' $d/seg.summary
done
echo "== cluster: per arm, from ds.csv / final-ls / system.log"
for d in $R/cluster/*/; do a=$(basename $d)
  [ -f $d/times.txt ] || continue
  . <(tr ' ' '\n' < $d/times.txt | sed 's/^/T_/')
  awk -F, -v A=$a -v S=$T_S 'NR>1{ if($3>mx)mx=$3; if($4>tot)tot=$4; if($2>nf)nf=$2; if($6>mp)mp=$6 } END{printf "%s S=%s maxfile=%d (%.3f MiB) peakfiles=%d peaktotal=%.1f MiB maps=%.1f MiB\n",A,S,mx,mx/1048576,nf,tot/1048576,mp/1048576}' $d/ds.csv
  echo "   names seen: $(tail -n +2 $d/ds.perfile.csv | wc -l); final ls sizes: $(awk 'NR>1 && $9 ~ /\.log$/ {print $5}' $d/final-ls.txt | sort -n | uniq -c | tr '\n' ' ')"
  echo "   system.log: segment_size=$(grep -ho 'commitlog_segment_size=[^;]*' $d/system.log | sort -u | tr '\n' ' ') non-system flush reasons: $(grep 'Enqueuing flush of' $d/system.log | grep -v ' system' | grep -o 'Reason: [A-Z_]*' | sort | uniq -c | tr '\n' ' ')"
  echo "   stress: $(grep -h 'Total errors' $d/stress.out $d/loader.out 2>/dev/null | head -1)"
done
