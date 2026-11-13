#!/usr/bin/env bash
# Fresh 10-instance ring (clean start: all instance dirs and tmpfs data regenerated).
#   ring-up.sh            env: DIRECT (victim direct MiB), BYTEMAN (btm path or empty), VEXTRA ("k=v k=v" yaml for V only)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=$H/ctl.sh
NT=/mydata/b6/cassandra/bin/nodetool
$C stop all >/dev/null
$C gen V 2G ${VEXTRA:-} || exit 1
$C gen F 8G || exit 1
for c in C1 C2 C3 C4 C5 C6 C7 C8; do $C gen $c 2G || exit 1; done
$C start V
for _ in $(seq 60); do $NT -p 7221 status 2>/dev/null | grep -q '^UN  127.0.0.21' && break; sleep 2; done
$C start F; sleep 6
for c in C1 C2 C3 C4 C5 C6 C7 C8; do $C start $c; sleep 4; done
n=0
for _ in $(seq 90); do
  n=$($NT -p 7221 status 2>/dev/null | grep -c '^UN'); [ "$n" = 10 ] && break; sleep 3
done
for ip in 22 31 32 33 34 35 36 37 38; do for _ in $(seq 40); do (exec 3<>/dev/tcp/127.0.0.$ip/9042) 2>/dev/null && break; sleep 2; done; done
echo "UN=$n"
[ "$n" = 10 ] && "$H/load.sh" schema 127.0.0.31
