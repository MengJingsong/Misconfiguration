#!/bin/bash
# Cluster tier, the labels in series. Usage: bash cluster-all.sh <outdir>
# Labels (tree / mode / chars / memtable_heap_space MiB / stop switches / row cap or count / in flight):
#  A1024c   s4-tm        CONTAINS 1023 256 3 600    1     main run, 1024 build
#  A1024c128 s4-tm       CONTAINS 1023 128 3 600    1     positive control: smaller pool
#  A1024r   s4-tm        CONTAINS 1024 256 0 <rows of A1024c at its third switch> 1   rejected term length
#  A1024n   s4-tm        NONE     1023 256 0 <same rows> 1                           index dropped
#  A1024p   s4-tm        PREFIX   1023 256 3 150000 64
#  A256c    s4-tm-c256   CONTAINS 255  256 3 6000  1
#  A4096c   s4-tm-c4096  CONTAINS 4095 256 3 60    1
# Stops at the first run whose summary.json has an error key. Node and sampler are stopped by cluster-run.py on any exit.
set -u
OUT=${1:?}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"; ulimit -n 100000
run() {  # label then key=value args
  l=$1; shift
  echo "[$(date -u +%FT%TZ)] run $l $*" | tee -a "$OUT/all.log"
  python3 "$H/cluster-run.py" "$l" "$@" outdir="$OUT/$l" > "$OUT/$l.out" 2>&1
  if grep -q '"error"' "$OUT/$l/summary.json" 2>/dev/null || [ ! -f "$OUT/$l/summary.json" ]; then echo "STOP: $l failed" | tee -a "$OUT/all.log"; exit 1; fi
}
run A1024c    tree=s4-tm mode=CONTAINS size=1023 heap_mb=256 stop=3 rows=600 inflight=1
ROWS=$(python3 - "$OUT/A1024c/rows.csv" <<'PY'
import sys
print(open(sys.argv[1]).read().strip().splitlines()[-1].split(',')[1])
PY
)
echo "A1024c loaded $ROWS rows" | tee -a "$OUT/all.log"
run A1024c128 tree=s4-tm mode=CONTAINS size=1023 heap_mb=128 stop=3 rows=600 inflight=1
run A1024r    tree=s4-tm mode=CONTAINS size=1024 heap_mb=256 stop=0 rows=$ROWS inflight=1
run A1024n    tree=s4-tm mode=NONE     size=1023 heap_mb=256 stop=0 rows=$ROWS inflight=1
run A1024p    tree=s4-tm mode=PREFIX   size=1023 heap_mb=256 stop=3 rows=150000 inflight=64
run A256c     tree=s4-tm-c256 mode=CONTAINS size=255 heap_mb=256 stop=3 rows=6000 inflight=1
run A4096c    tree=s4-tm-c4096 mode=CONTAINS size=4095 heap_mb=256 stop=3 rows=60 inflight=1
echo "[$(date -u +%FT%TZ)] all done" | tee -a "$OUT/all.log"
