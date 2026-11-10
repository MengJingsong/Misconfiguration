#!/usr/bin/env bash
# Fresh 3-instance ring (clean start): ring-up.sh <S_xmx> [S yaml key=value ...]
# S always gets the extra keys; V/F get write_request_timeout/native_transport_timeout matching S if given.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=$H/ctl.sh
SX=${1:?S xmx}; shift
$C stop all >/dev/null
$C gen V ${VXMX:-2G} "$@" && $C gen F 8G "$@" && $C gen S "$SX" "$@" || exit 1
$C start V; sleep 35; $C start F; sleep 35; $C start S
for _ in $(seq 40); do
  n=$(/mydata/b6/cassandra/bin/nodetool -p 7213 status 2>/dev/null | grep -c '^UN')
  [ "$n" = 3 ] && break; sleep 3
done
for _ in $(seq 30); do (exec 3<>/dev/tcp/127.0.0.13/9042) 2>/dev/null && break; sleep 2; done
echo "UN=$n"; [ "$n" = 3 ] && python3 "$H/load.py" schema
