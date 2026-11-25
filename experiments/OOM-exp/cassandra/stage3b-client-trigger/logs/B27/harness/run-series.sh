#!/usr/bin/env bash
# B27 3-b confirm (2026-11-24, pc99): runs the given run-list lines in order in one detached driver.
# usage: run-series.sh <list file>   (line: <run-id> <arm> <heap GiB> <spec> [extra args]; '#' = comment)
cd /mydata/s4/3b-B27
while read -r id arm h spec rest; do
  case "$id" in ''|\#*) continue ;; esac
  [ -e logs/STOP-SERIES ] && { echo "STOP-SERIES present, not starting $id"; break; }
  echo "$id start $(date +%T)"
  python3 harness/b27-3b-run.py run "$id" "$arm" "$h" "$spec" 200000 $rest > logs/$id.driver.txt 2>&1
  echo "$id rc=$? $(date +%T) $(grep -m1 '^endpoint:' logs/$id/summary.txt) $(grep -m1 '^endpoint_t_s:' logs/$id/summary.txt)"
done < "$1"
echo SERIES-DONE $(date +%T)
