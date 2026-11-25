#!/usr/bin/env bash
# R23 series driver (design 2.5 "Order", after S0, mk-A1 and the D* ladder): D* = 100 ms (K100b met G2, amendment A1).
# T1 C1 I1 N1 | mk-A2 T2 C2 I2 | mk-A3 T3 C3 I3 | U-search (2.7) | N2 N3 only if N1 died.
# No arm starts after the cutoff (13:30 America/New_York), with < 5 GiB free on /mydata, or with a STOP file.
set -uo pipefail
W=/mydata/s4/r23; H=$W/harness; SL=$W/series.log; DS=100
CUT=$(TZ=America/New_York date -d '2026-11-24 13:30' +%s)
slog() { echo "[$(date +%T)] $*" | tee -a $SL; }
ok() { local n=$(date +%s) f=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
  [ $n -ge $CUT ] && { slog "STOP: cutoff reached before $1"; return 1; }
  [ $f -lt 5 ] && { slog "STOP: /mydata free ${f}G < 5G before $1"; return 1; }
  [ -e $W/STOP ] && { slog "STOP: STOP file before $1"; return 1; }; return 0; }
res() { grep -o 'outcome=[a-z]*' $W/runs/$1/arm.log | tail -1 | cut -d= -f2; }
mk() { ok mk-$1 || exit 0; slog "mk-$1"; bash $H/mkimg.sh $1 > /dev/null 2>&1; slog "$(tail -1 $W/runs/mk-$1/arm.log)"; }
rp() { local run=$1; shift; ok $run || exit 0; slog "$run $*"; bash $H/restore.sh $run "$@" > /dev/null 2>&1; slog "$(tail -1 $W/runs/$run/arm.log)"; }
I64=-Dcassandra.commitlog_max_outstanding_replay_count=64
slog "== series start; D*=$DS ms; cutoff $(date -d @$CUT +%T)"
for k in ${TRIPLES:-1 2 3}; do
  [ $k = 1 ] || mk A$k
  rp T$k A$k 1024 $DS T
  rp C$k A$k 1024 $DS C
  rp I$k A$k 1024 $DS T $I64
  [ $k = 1 ] && rp N1 A1 1024 0 T
done
# upward search (2.7)
rp U1536 A1 1536 $DS T
if [ "$(res U1536)" = died ]; then
  rp U2048a A2 2048 $DS T
  if [ "$(res U2048a)" = died ]; then rp U2048b A3 2048 $DS T; rp U3072 A1 3072 $DS T; fi
else
  rp U1280 A2 1280 $DS T
fi
if [ "$(res N1)" = died ]; then rp N2 A2 1024 0 T; rp N3 A3 1024 0 T; fi
slog "== series end"
