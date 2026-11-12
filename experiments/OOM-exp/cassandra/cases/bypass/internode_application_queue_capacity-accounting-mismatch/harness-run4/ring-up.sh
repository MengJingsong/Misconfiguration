#!/usr/bin/env bash
# Fresh 4-instance ring (clean start), disk delay reset to 0.
#   ring-up.sh <S_xmx> [yaml key=value ... for all instances]
# Replicas V1, V2 at ${VXMX:-8G}, F at 8G. Schema: NTS {v:1, f:1} (B6Load schema).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=$H/ctl.sh; H2=$H/../harness-run2
SX=${1:?}; shift
$C stop all >/dev/null
"$H2/slowdisk.sh" set 0
$C gen V1 "${VXMX:-8G}" "$@" && $C gen V2 "${VXMX:-8G}" "$@" && $C gen F 8G "$@" && $C gen S "$SX" "$@" || exit 1
$C start V1; sleep 35; $C start V2; sleep 30; $C start F; sleep 30; $C start S
for _ in $(seq 40); do
  n=$(/mydata/b6/cassandra/bin/nodetool -p 7211 status 2>/dev/null | grep -c '^UN'); [ "$n" = 4 ] && break; sleep 3
done
for _ in $(seq 30); do (exec 3<>/dev/tcp/127.0.0.13/9042) 2>/dev/null && break; sleep 2; done
echo "UN=$n"; [ "$n" = 4 ] && "$H2/load.sh" schema 127.0.0.13
