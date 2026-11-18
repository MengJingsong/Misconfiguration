#!/usr/bin/env bash
# B10 stage 2: after the 2 GiB set: repeat of the invalid C2-r1 start (C2-r1b), then the upward search of §2.9:
# T4 x1 -> if OOM, T8 x1 -> repeat the largest failing heap to 3 runs. No new run starts after 01:55 EST.
cd /mydata/s4/b10-w1
while ! grep -q SET-DONE logs/set-2g.txt; do sleep 5; done
late() { [ "$(TZ=America/New_York date +%H%M)" -ge 0155 ] && [ "$(TZ=America/New_York date +%H%M)" -lt 1200 ]; }
oom() { grep -q '^endpoint: OOM' logs/$1/summary.txt; }
go() { id=$1; shift
  if [ -e logs/STOP-SET ] || late; then echo "not starting $id (stop file or 01:55 cut-off)"; return 1; fi
  python3 harness/b10-run.py run $id "$@" > logs/$id.driver.txt 2>&1; echo "$id rc=$? $(date +%T)"
  f=$(ls logs/$id/*.hprof 2>/dev/null | head -1)
  [ -n "$f" ] && nice -n 19 ionice -c3 python3 harness/hprof-histo.py $f > logs/$id/hprof-histo.txt 2>&1 &
  return 0; }
go C2-r1b C2 2 8 200000
go T4-r1 T4 4 40 200000
if oom T4-r1; then
  go T8-r1 T8 8 80 200000
  if oom T8-r1; then go T8-r2 T8 8 80 200000; go T8-r3 T8 8 80 200000
  else go T4-r2 T4 4 40 200000; go T4-r3 T4 4 40 200000; fi
fi
wait
echo SEARCH-DONE
