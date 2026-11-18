#!/usr/bin/env bash
# B10 stage 2: T8 repeats. T8-r1 reached heap OOM but its driver aborted on a hung histogram (fixed), so the search
# script took its "no OOM" branch (T4-r2, T4-r3). This adds the design's repeats of the largest failing heap.
cd /mydata/s4/b10-w1
while ! grep -q SEARCH-DONE logs/set-search.txt; do sleep 5; done
late() { h=$(TZ=America/New_York date +%H%M); [ "$h" -ge 0155 ] && [ "$h" -lt 1200 ]; }
for id in T8-r2 T8-r3; do
  if [ -e logs/STOP-SET ] || late; then echo "not starting $id"; break; fi
  python3 harness/b10-run.py run $id T8 8 80 200000 > logs/$id.driver.txt 2>&1; echo "$id rc=$? $(date +%T)"
done
echo T8-DONE
