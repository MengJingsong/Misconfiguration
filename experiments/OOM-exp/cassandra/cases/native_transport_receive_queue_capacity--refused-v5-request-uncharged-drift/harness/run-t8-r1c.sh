#!/usr/bin/env bash
# B10 stage 2, resumed 2026-11-18: T8-r1b did not start (the driver's process check matched the launching ssh
# command line, as C2-r1 did). After run-t8-redo.sh: one more T8 run at MemoryMax 18 GiB as the third T8 repeat.
cd /mydata/s4/b10-w1
while ! grep -q T8-REDO-DONE logs/set-t8-redo.txt; do sleep 5; done
late() { h=$(TZ=America/New_York date +%H%M); [ "$h" -ge 0630 ] && [ "$h" -lt 1200 ]; }
id=T8-r1c
if [ -e logs/STOP-SET ] || late; then echo "not starting $id"; else
  B10_MEMMAX_ADD=10 python3 harness/b10-run.py run $id T8 8 80 200000 > logs/$id.driver.txt 2>&1; echo "$id rc=$? $(date +%T)"
  f=$(ls logs/$id/*.hprof 2>/dev/null | head -1)
  [ -n "$f" ] && nice -n 19 ionice -c3 python3 harness/hprof-histo.py $f > logs/$id/hprof-histo.txt 2>&1
fi
echo T8-R1C-DONE
