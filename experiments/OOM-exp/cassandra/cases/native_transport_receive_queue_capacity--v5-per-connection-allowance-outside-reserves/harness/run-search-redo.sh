#!/usr/bin/env bash
# B27 stage 2 (2026-11-24 16:10 EST): T4-r1..r3 had scope memory.events max > 0 (the OOM heap dump's page cache filled
# the 12-GiB containment scope after the heap OOM) and are invalid by design §2.3; each is repeated once with
# MemoryMax + 4 GiB (B27_MEMMAX_ADD=10 -> 16 GiB). T8 starts at the same +4 GiB headroom (22 GiB): containment only.
cd /mydata/s4/b27
until grep -q -E "SEARCH-DONE|STOP-SET" logs/set-search.txt 2>/dev/null; do sleep 10; done
rm -f logs/STOP-SET
export B27_MEMMAX_ADD=10
t4oom=0
for r in "T4-r1b T4 4 2 7000" "T4-r2b T4 4 2 7000" "T4-r3b T4 4 2 7000" "T8-r1 T8 8 4 14000" "T8-r2 T8 8 4 14000" "T8-r3 T8 8 4 14000"; do
  set -- $r; id=$1; arm=$2
  if [ -e logs/STOP-SET ]; then echo "STOP-SET present, not starting $id"; break; fi
  if [ "$arm" = T8 ] && [ $t4oom -eq 0 ]; then echo "no valid T4 OOM, T8 not run"; break; fi
  python3 harness/b27-run.py run $id $arm $3 $4 $5 200000 > logs/$id.driver.txt 2>&1
  echo "$id rc=$? $(date +%T) $(grep -m1 '^endpoint:' logs/$id/summary.txt) $(grep -m1 '^scope_events:' logs/$id/summary.txt)"
  [ "$arm" = T4 ] && grep -q '^endpoint: OOM' logs/$id/summary.txt && t4oom=1
done
echo REDO-DONE $(date +%T)
