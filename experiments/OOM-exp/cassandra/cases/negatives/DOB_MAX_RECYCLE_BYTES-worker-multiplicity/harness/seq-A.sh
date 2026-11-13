#!/usr/bin/env bash
# C3 phase A (2026-11-12): U vs T at matched fill traffic (4000 x 520,000 B), direct 2048 MiB (non-binding), heap 2048 MiB.
cd /mydata/c3
for spec in "A-c1 1 1" "A-c4 4 1" "A-c16 16 1" "A-c64 64 1" "A-c256 256 1" "A-c512x4 512 4"; do
  set -- $spec
  tools/c3-run.sh arm "$1" 2048 default "$2" "$3" none dump > "logs/$1.out" 2>&1 < /dev/null
  echo "[$(date +%T)] $1 rc=$?"
done
echo SEQ-A DONE
