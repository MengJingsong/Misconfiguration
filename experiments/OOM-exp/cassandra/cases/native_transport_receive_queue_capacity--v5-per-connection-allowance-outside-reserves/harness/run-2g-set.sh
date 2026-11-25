#!/usr/bin/env bash
# B27 stage 2 (2026-11-24): the 2 GiB set on pc82, T2 run 1 first (dose-ladder check: the set is stopped with
# logs/STOP-SET if T2-r1 ends without OOM), then C2 / I2 / T2 interleaved, then the supporting X2 and I2b.
cd /mydata/s4/b27
I2X='native_transport_max_concurrent_connections: 1000'
I2BX='native_transport_receive_queue_capacity: 0B'
while read -r id arm h d n rest; do
  [ -z "$id" ] && continue
  if [ -e logs/STOP-SET ]; then echo "STOP-SET present, not starting $id"; break; fi
  case $arm in
    I2)  python3 harness/b27-run.py run $id $arm $h $d $n 200000 --extra "$I2X" $rest > logs/$id.driver.txt 2>&1 ;;
    I2b) python3 harness/b27-run.py run $id $arm $h $d $n 200000 --extra "$I2BX" --throw $rest > logs/$id.driver.txt 2>&1 ;;
    *)   python3 harness/b27-run.py run $id $arm $h $d $n 200000 $rest > logs/$id.driver.txt 2>&1 ;;
  esac
  echo "$id rc=$? $(date +%T)"
done <<'RUNS'
T2-r1 T2 2 2 3500
C2-r1 C2 2 2 1000
I2-r1 I2 2 2 3500
T2-r2 T2 2 2 3500
C2-r2 C2 2 2 1000
I2-r2 I2 2 2 3500
T2-r3 T2 2 2 3500
C2-r3 C2 2 2 1000
I2-r3 I2 2 2 3500
X2-r1 X2 2 2 3500 --window 0
I2b-r1 I2b 2 2 3500
RUNS
echo SET-DONE $(date +%T)
