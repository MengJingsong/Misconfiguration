#!/usr/bin/env bash
# B27 stage 2 (2026-11-24): the upward budget search on pc82 after the 2 GiB set: T4 (heap 4 / direct 2 GiB, N = 7,000)
# x 3, then T8 (heap 8 / direct 4 GiB, N = 14,000) x 3 only if a T4 run reached OOM (design §2.7).
cd /mydata/s4/b27
until grep -q SET-DONE logs/set-2g.txt 2>/dev/null; do sleep 20; done
t4oom=0
for r in "T4-r1 T4 4 2 7000" "T4-r2 T4 4 2 7000" "T4-r3 T4 4 2 7000" "T8-r1 T8 8 4 14000" "T8-r2 T8 8 4 14000" "T8-r3 T8 8 4 14000"; do
  set -- $r; id=$1; arm=$2
  if [ -e logs/STOP-SET ]; then echo "STOP-SET present, not starting $id"; break; fi
  if [ "$arm" = T8 ] && [ $t4oom -eq 0 ]; then echo "no T4 OOM, T8 not run"; break; fi
  python3 harness/b27-run.py run $id $arm $3 $4 $5 200000 > logs/$id.driver.txt 2>&1
  echo "$id rc=$? $(date +%T) $(grep -m1 '^endpoint:' logs/$id/summary.txt)"
  [ "$arm" = T4 ] && grep -q '^endpoint: OOM' logs/$id/summary.txt && t4oom=1
done
echo SEARCH-DONE $(date +%T)
