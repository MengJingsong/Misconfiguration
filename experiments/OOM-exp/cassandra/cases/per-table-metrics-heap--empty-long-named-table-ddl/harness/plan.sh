#!/usr/bin/env bash
# U14 sequence runner: one lifetime per plan line "<label> <arm> <heap> <names> <N> [<X>]", in order; run.py refuses a start
# after 13:15 New York (exit 2) and the runner then stops. A line starting with '#' is skipped.
W=/mydata/s4/u14; P=$1
while read -r label arm heap names n x; do
  [ -z "$label" ] && continue; [[ "$label" == \#* ]] && continue
  echo "$(TZ=America/New_York date '+%F %T') start $label $arm $heap $names $n $x"
  python3 -I $W/harness/run.py life $label $arm $heap $names $n $x > $W/logs/$label.out 2>&1
  rc=$?
  rm -f $W/dumps/$label/*.hprof   # dumps are scanned inside run.py; only H2-T-1's (earlier) dump is kept
  echo "$(TZ=America/New_York date '+%F %T') end $label rc=$rc"
  [ $rc -eq 2 ] && { echo "stop: no start after 13:15"; break; }
  [ -e $W/plan.stop ] && { echo "stop: plan.stop"; break; }
done < "$P"
echo "$(TZ=America/New_York date '+%F %T') plan done"
