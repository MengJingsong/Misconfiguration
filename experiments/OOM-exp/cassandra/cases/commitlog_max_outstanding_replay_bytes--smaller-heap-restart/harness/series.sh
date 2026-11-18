#!/usr/bin/env bash
# B15 series driver (design 2.5 "Order"): mk-L1 N1 T1 mk-K1 C1 I1 | mk-L2 T2 mk-K2 C2 I2 | mk-L3 T3 mk-K3 C3 I3 | U-search | N2 N3.
# No arm starts after NO_NEW_AFTER (epoch s; 10:20 America/New_York) or with < 5 GiB free on /mydata.
# K images are deleted after their C/I use. Writes $W/series.log.
set -uo pipefail
W=/mydata/s4/b15-w3; H=$W/harness; SL=$W/series.log
CUT=$(TZ=America/New_York date -d '2026-11-18 10:20' +%s)
slog() { echo "[$(date +%T)] $*" | tee -a $SL; }
ok() { local n=$(date +%s) f=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
  [ $n -ge $CUT ] && { slog "STOP: cutoff 10:20 reached before $1"; return 1; }
  [ $f -lt 5 ] && { slog "STOP: /mydata free ${f}G < 5G before $1"; return 1; }
  [ -e $W/STOP ] && { slog "STOP: STOP file before $1"; return 1; }; return 0; }
res() { grep -o 'outcome=[a-z]*' $W/runs/$1/arm.log | tail -1 | cut -d= -f2; }
mk() { ok mk-$1 || exit 0; slog "mk-$1 (writer $2)"; bash $H/mkimg.sh $1 $2 > /dev/null 2>&1; slog "$(tail -1 $W/runs/mk-$1/arm.log)"; }
rp() { local run=$1; shift; ok $run || exit 0; slog "$run $*"; bash $H/replay.sh $run "$@" > /dev/null 2>&1; slog "$(tail -1 $W/runs/$run/arm.log)"; }
I64=-Dcassandra.commitlog_max_outstanding_replay_count=64
slog "== series start; cutoff $(date -d @$CUT +%T)"
for k in ${TRIPLES:-1 2 3}; do
  mk L$k 8192
  [ $k = 1 ] && rp N1 L1 1024 0
  rp T$k L$k 1024 1
  mk K$k 1024
  rp C$k K$k 1024 1
  rm -rf $W/img/K$k
  rp I$k L$k 1024 1 $I64
done
# upward search (2.7)
rp U1536 L1 1536 1
if [ "$(res U1536)" = died ]; then
  rp U2048a L2 2048 1
  [ "$(res U2048a)" = died ] && rp U2048b L3 2048 1
else
  rp U1280 L2 1280 1
fi
rp N2 L2 1024 0
rp N3 L3 1024 0
slog "== series end"
