#!/bin/bash
# Run 1 cluster tier: all labelled runs in order. Usage: bash cluster-all.sh <outroot>
# Stops at the first run whose trigger check fails (no stream window, or B not up in a non-cap run).
OUT=${1:?}; H=$(dirname "$0"); mkdir -p "$OUT"
RUNS="r01_c16:16:0:normal r02_c64:64:0:normal r03_c4:4:0:normal r04_c1024_r0:1024:0:normal r05_c1024_r11:1024:1.1:normal r06_c16384_r0_a:16384:0:normal r07_c16384_r11_a:16384:1.1:normal r08_c16384_r0_b:16384:0:normal r09_c16384_r11_b:16384:1.1:normal r10_cap100m_c16384:16384:0:cap r11_entire_c16384:16384:0:entire"
for spec in $RUNS; do
  IFS=: read label chunk ratio mode <<< "$spec"
  echo "[$(date -u +%FT%TZ)] START $label" >> $OUT/chain.log
  python3 $H/cluster-run.py $label $chunk $ratio $mode $OUT/$label 256 1048576 > $OUT/$label.out 2>&1
  python3 $H/analyze_cluster.py $OUT/$label >> $OUT/analysis.jsonl 2>> $OUT/chain.log
  echo "[$(date -u +%FT%TZ)] END $label rc=$?" >> $OUT/chain.log
  if ! python3 - "$OUT/$label" "$mode" <<'PY'
import json,sys
d,mode=sys.argv[1:3]
try:
    s=json.load(open(d+'/summary.json'))
except Exception as e:
    sys.exit(1)
ok = 'error' not in s and (mode=='cap' or s.get('B_outcome')=='B_UN_binary_running')
sys.exit(0 if ok else 1)
PY
  then echo "[$(date -u +%FT%TZ)] STOP: first-trigger check failed at $label" >> $OUT/chain.log; exit 1; fi
done
echo "[$(date -u +%FT%TZ)] ALL DONE" >> $OUT/chain.log
