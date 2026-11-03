#!/usr/bin/env bash
# Run 1 order of the cluster tier (B3e amended): 4MiB, 32MiB, auto (N = 20000 each), then the control C_ctl / N_ctl
# computed from the 4 MiB run's final prepared_statements_count (B3b amended).
# Env: OUT (log root). Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$W/logs/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/cluster}; export OUT
mkdir -p "$OUT"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$OUT/chain.out"; }
say "chain start"
"$H/cluster-run.sh" k4 4MiB main 20000; say "k4 rc=$?"
CNT=$(tail -1 "$OUT/k4/samples.csv" | cut -d, -f3)
read NCTL CCTL WBAR < <(python3 -I -c "
import math,sys
cnt=int(sys.argv[1]); w=4194304/cnt
n=min(20000, int(629145600 // w // 2)); c=math.ceil(2*n*w/1048576)
print(n, c, '%.1f' % w)" "$CNT")
say "CALIBRATION count_at_4MiB=$CNT wbar=$WBAR N_ctl=$NCTL C_ctl=${CCTL}MiB"
"$H/cluster-run.sh" k32 32MiB main 20000; say "k32 rc=$?"
"$H/cluster-run.sh" kauto auto main 20000; say "kauto rc=$?"
"$H/cluster-run.sh" ctl "${CCTL}MiB" control "$NCTL"; say "ctl rc=$?"
say "chain end"
