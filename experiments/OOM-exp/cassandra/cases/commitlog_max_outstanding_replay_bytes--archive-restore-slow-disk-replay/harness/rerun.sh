#!/usr/bin/env bash
# R23 re-runs after amendment A2 (arms killed by the A1 pre-attach race): T3 I3 on A3; upward search per 2.7 with the valid
# U2048b (A3, run out of order) counted: U1536 A1; if died -> U2048a A2; if both 2048 died -> U3072 A1; else U1280 A2.
set -uo pipefail
W=/mydata/s4/r23; H=$W/harness; SL=$W/series.log; DS=100
CUT=$(TZ=America/New_York date -d '2026-11-24 13:30' +%s)
slog() { echo "[$(date +%T)] $*" | tee -a $SL; }
ok() { [ $(date +%s) -ge $CUT ] && { slog "STOP: cutoff before $1"; return 1; }; [ -e $W/STOP ] && { slog "STOP: STOP file before $1"; return 1; }; return 0; }
res() { grep -o 'outcome=[a-z]*' $W/runs/$1/arm.log | tail -1 | cut -d= -f2; }
rp() { local run=$1; shift; ok $run || exit 0; slog "$run $*"; bash $H/restore.sh $run "$@" > /dev/null 2>&1; slog "$(grep '== RESULT' $W/runs/$run/arm.log | tail -1)"; }
I64=-Dcassandra.commitlog_max_outstanding_replay_count=64
slog "== rerun start (amendment A2)"
for r in T3 I3 U1536 U2048a; do [ -d $W/runs/$r ] && mv $W/runs/$r $W/runs/$r-invalidA1; done
rp T3 A3 1024 $DS T
rp I3 A3 1024 $DS T $I64
rp U1536 A1 1536 $DS T
if [ "$(res U1536)" = died ]; then
  rp U2048a A2 2048 $DS T
  if [ "$(res U2048a)" = died ] && [ "$(res U2048b)" = died ]; then rp U3072 A1 3072 $DS T; fi
else
  rp U1280 A2 1280 $DS T
fi
slog "== rerun end"
