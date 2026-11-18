#!/usr/bin/env bash
# B10 stage 2: the remaining 2 GiB runs, interleaved C2, I2, T2 (T2 run 1 ran alone first for the dose-ladder check).
cd /mydata/s4/b10-w1
for r in "C2-r1 C2 2 8" "I2-r1 I2 2 20 --throw" "T2-r2 T2 2 20" "C2-r2 C2 2 8" "I2-r2 I2 2 20 --throw" "T2-r3 T2 2 20" "C2-r3 C2 2 8" "I2-r3 I2 2 20 --throw"; do
  set -- $r; id=$1; arm=$2; h=$3; n=$4; shift 4
  if [ -e logs/STOP-SET ]; then echo "STOP-SET present, not starting $id"; break; fi
  python3 harness/b10-run.py run $id $arm $h $n 200000 "$@" > logs/$id.driver.txt 2>&1
  echo "$id rc=$? $(date +%T)"
done
echo SET-DONE
