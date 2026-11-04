#!/usr/bin/env bash
# Unit tier (B2) of seed_count_warn_threshold-getseeds-seeds_size--autonomous. One JVM per cell.
# Arms: U = unmodified copy ($A, default ~/s4-base), P = copy with the list truncated to the threshold ($B, default ~/s4-seed-b; positive control).
# usage: unit-run.sh [reps]   output ~/stage4-logs/seed/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); A=${A:-$HOME/s4-base}; B=${B:-$HOME/s4-seed-b}; L=$HOME/stage4-logs/seed/unit; REPS=${1:-3}
mkdir -p "$L"
for T in $A $B; do cp "$H/SeedCountFootprintTest.java" "$T/test/unit/org/apache/cassandra/locator/"; done
for T in $A $B; do echo "tree $T: $(git -C $T describe --tags) diff: $(git -C $T diff --stat | tail -1)" | tee -a "$L/summary.txt"; done
seeds() { python3 -c "import sys;k=int(sys.argv[1]);print(','.join('10.%d.%d.%d'%(i//62500,(i//250)%250,i%250+1) for i in range(k)))" "$1"; }
run() { # <arm> <tree> <K> <thr|default> <rep>
  local lab="$1-k$3-t$4-r$5" y="$L/cassandra-k$3.yaml"
  seeds $3 > "$L/seeds-$3.txt"      # a file, not argv: 20000 seeds exceed the single-argument limit (runbook defect 2)
  python3 - "$2/test/conf/cassandra.yaml" "$y" "$L/seeds-$3.txt" <<'PY'
import re,sys
t=open(sys.argv[1]).read(); s=open(sys.argv[3]).read().strip()
t=re.sub(r'(seeds:\s*)"[^"]*"', lambda m: m.group(1)+'"'+s+'"', t, count=1)
open(sys.argv[2],'w').write(t)
PY
  grep -c '^          - seeds:' "$y" > /dev/null || { echo "seeds line missing"; exit 1; }
  local thr=""; [ "$4" != default ] && thr="-Dcassandra.seed_count_warn_threshold=$4"
  (cd "$2" && ant testsome -Dtest.name=org.apache.cassandra.locator.SeedCountFootprintTest \
    -Dtest.jvm.args="-Dcassandra.config=file://$y $thr -Dstage4.out=$L/run.out -Dstage4.arm=$1 -Dstage4.k=$3 -Dstage4.rep=$5" </dev/null > "$L/ant-$lab.log" 2>&1)
  echo "$lab: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$lab.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"; }
for r in $(seq 1 $REPS); do
  for k in 25 1000 20000; do
    run U $A $k default $r        # threshold 20 (default literal), below K: WARN
    run U $A $k $((k*2)) $r       # threshold above K: no WARN
    run P $B $k default $r        # positive control: a real cap (list truncated to the threshold)
  done
done
echo "cells: $(grep -c 'STAGE4 final' "$L/run.out")" | tee -a "$L/summary.txt"
