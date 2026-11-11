#!/usr/bin/env bash
# Fresh 6-instance ring (clean start), disk delay reset to 0.
#   ring-up.sh <V_xmx> <S_xmx> [yaml key=value ... for all instances]
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=$H/ctl.sh
VX=${1:?}; SX=${2:?}; shift 2
$C stop all >/dev/null
"$H/slowdisk.sh" set 0
$C gen V "$VX" "$@" && $C gen F 8G "$@" || exit 1
for s in S1 S2 S3 S4; do $C gen $s "$SX" "$@" || exit 1; done
$C start V; sleep 35; $C start F; sleep 30
for s in S1 S2 S3 S4; do $C start $s; sleep 25; done
for _ in $(seq 40); do
  n=$(/mydata/b6/cassandra/bin/nodetool -p 7211 status 2>/dev/null | grep -c '^UN'); [ "$n" = 6 ] && break; sleep 3
done
for ip in 13 14 15 16; do for _ in $(seq 30); do (exec 3<>/dev/tcp/127.0.0.$ip/9042) 2>/dev/null && break; sleep 2; done; done
echo "UN=$n"; [ "$n" = 6 ] && "$H/load.sh" schema 127.0.0.13
