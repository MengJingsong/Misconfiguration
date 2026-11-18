#!/usr/bin/env bash
# B10 stage 2, resumed 2026-11-18 after an interruption: repeat the T8 condition once per non-reading run.
# T8-r1 (driver aborted on a hung histogram, no summary) -> T8-r1b; T8-r2, T8-r3 (scope memory.events max > 0,
# invalid under design §2.3) -> T8-r2b, T8-r3b, each with MemoryMax + 4 GiB (heap 8 + 10 = 18 GiB).
# hprof class histogram of each dump after the run (nice/ionice). No new run starts after 06:30 EST.
cd /mydata/s4/b10-w1
late() { h=$(TZ=America/New_York date +%H%M); [ "$h" -ge 0630 ] && [ "$h" -lt 1200 ]; }
for id in T8-r1b T8-r2b T8-r3b; do
  if [ -e logs/STOP-SET ] || late; then echo "not starting $id"; break; fi
  B10_MEMMAX_ADD=10 python3 harness/b10-run.py run $id T8 8 80 200000 > logs/$id.driver.txt 2>&1; echo "$id rc=$? $(date +%T)"
  f=$(ls logs/$id/*.hprof 2>/dev/null | head -1)
  [ -n "$f" ] && nice -n 19 ionice -c3 python3 harness/hprof-histo.py $f > logs/$id/hprof-histo.txt 2>&1
done
for id in T8-r2 T8-r3; do
  f=$(ls logs/$id/*.hprof 2>/dev/null | head -1)
  [ -n "$f" ] && [ ! -s logs/$id/hprof-histo.txt ] && nice -n 19 ionice -c3 python3 harness/hprof-histo.py $f > logs/$id/hprof-histo.txt 2>&1
done
echo T8-REDO-DONE
