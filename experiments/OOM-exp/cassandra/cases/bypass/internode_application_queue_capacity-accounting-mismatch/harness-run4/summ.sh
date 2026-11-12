#!/usr/bin/env bash
# One line per run-4 arm: outcome, all-STW service-loss check, client totals and rate during the first
# 20 s (before the stall), peak S->V1/V2 send-queue counters (K), V1/V2 receive using, foreign load.
#   summ.sh <arm-dir>...
for R in "$@"; do
  n=$(basename "$R")
  o=$(head -1 "$R/outcome.txt" | sed 's/ | pauses=.*max_after_full=/ live_after_full=/; s/ ReportJava.*//')
  w=$(grep -h "service_loss(all STW)" "$R/outcome.txt" | tail -1 | sed 's/pauses=[0-9]* //')
  c=$(grep FINAL "$R/load.log" | awk '{print $2, $3, $4}')
  r20=$(grep -m1 "t=20s" "$R/load.log" | grep -o 'ok=[0-9]*' | awk -F= '{printf "%.0f/s", $2/20}')
  k=$(awk -F'|' '{split($1,a," "); ip=a[2]; gsub(/ /,"",$3); gsub(/ /,"",$5); gsub(/ /,"",$6); if ($3+0>mx[ip]) mx[ip]=$3+0; ov[ip]=$5; ex[ip]=$6}
       END{for (i in mx) printf "%s:peak_pending=%.1fMiB,overload=%s,expired=%s ", i, mx[i]/1048576, ov[i], ex[i]}' "$R/sout.log" 2>/dev/null)
  u=$(awk '{ip=$2; for(i=1;i<=NF;i++) if($i=="|"){f=$(i+1); break} if (f+0>m[ip]) m[ip]=f+0} END{for (i in m) printf "%s:max_using=%.1fMiB ", i, m[i]/1048576}' "$R/vin.log" 2>/dev/null)
  fj=$(awk '{for(i=4;i<=NF;i++) if ($i ~ /^[0-9]+$/) f=1} END{print (f? "foreign_java=yes" : (NR? "foreign_java=no" : "foreign=unrecorded"))}' "$R/foreign.txt" 2>/dev/null || echo foreign=unrecorded)
  echo "$n | $(cat "$R/args.txt" | sed 's/args: //') | $o | $w | client $c, pre-stall $r20 | $k| $u| $fj"
done
