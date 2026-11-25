#!/usr/bin/env bash
# B27 stage 2, attempt 3 (2026-11-24 20:10 EST, fresh session) on pc91: the whole frozen run list in one driver.
# Earlier attempts on pc82 were interrupted (owner stop ~16:25, API limit ~18:03); every run is repeated here from a
# clean start. Containment headroom (not a budget, design §2.3): T2/C2/I2/X2/I2b at the design's H + D + 6 GiB; T4 and
# T8 start at the "+4 GiB" retry headroom (H + D + 10 GiB) and T8 at H + D + 18 GiB, because on pc82 the OOM heap
# dump's page cache filled the 12-GiB (T4) and 22-GiB (T8) scopes (memory.events max > 0, invalid by §2.3).
# Dose-ladder check: if T2-r1 ends without OOM the driver stops (logs/STOP-SET) for a decision.
cd /mydata/s4/b27
I2X='native_transport_max_concurrent_connections: 1000'
I2BX='native_transport_receive_queue_capacity: 0B'
t4oom=0
while read -r id arm h d n add rest; do
  [ -z "$id" ] && continue
  if [ -e logs/STOP-SET ]; then echo "STOP-SET present, not starting $id"; break; fi
  if [ "$arm" = T8 ] && [ $t4oom -eq 0 ]; then echo "no valid T4 OOM, T8 not run"; break; fi
  export B27_MEMMAX_ADD=$add
  case $arm in
    I2)  python3 harness/b27-run.py run $id $arm $h $d $n 200000 --extra "$I2X" $rest > logs/$id.driver.txt 2>&1 ;;
    I2b) python3 harness/b27-run.py run $id $arm $h $d $n 200000 --extra "$I2BX" --throw $rest > logs/$id.driver.txt 2>&1 ;;
    *)   python3 harness/b27-run.py run $id $arm $h $d $n 200000 $rest > logs/$id.driver.txt 2>&1 ;;
  esac
  rc=$?
  echo "$id rc=$rc $(date +%T) $(grep -m1 '^endpoint:' logs/$id/summary.txt) $(grep -m1 '^scope_events:' logs/$id/summary.txt)"
  if [ "$id" = T2-r1 ] && ! grep -q '^endpoint: OOM' logs/$id/summary.txt; then touch logs/STOP-SET; fi
  [ "$arm" = T4 ] && grep -q '^endpoint: OOM' logs/$id/summary.txt && grep -q "'max': '0'" logs/$id/summary.txt && t4oom=1
done <<'RUNS'
T2-r1 T2 2 2 3500 6
C2-r1 C2 2 2 1000 6
I2-r1 I2 2 2 3500 6
T2-r2 T2 2 2 3500 6
C2-r2 C2 2 2 1000 6
I2-r2 I2 2 2 3500 6
T2-r3 T2 2 2 3500 6
C2-r3 C2 2 2 1000 6
I2-r3 I2 2 2 3500 6
X2-r1 X2 2 2 3500 6 --window 0
I2b-r1 I2b 2 2 3500 6
T4-r1 T4 4 2 7000 10
T4-r2 T4 4 2 7000 10
T4-r3 T4 4 2 7000 10
T8-r1 T8 8 4 14000 18
T8-r2 T8 8 4 14000 18
T8-r3 T8 8 4 14000 18
RUNS
echo SET-DONE $(date +%T)
