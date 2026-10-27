#!/usr/bin/env bash
# Cluster tier chain: nine node lifetimes (cache MiB x markers), then `down`. usage: chain.sh <run-name> [first-arm-only]
# EXPECTED: every arm prints "STOPPED: no daemon of this slot left"; the first arm (10 MiB, M=65535) passes the 65536 rejection check, else the chain stops.
# Output ~/s4-b9-bt-logs/<run>/cluster/c<MiB>-m<M>/ ; chain.status in ~/s4-b9-bt-logs/<run>/.  Launch: ( setsid nohup bash chain.sh run1 < /dev/null > /dev/null 2>&1 & )
H=$(cd "$(dirname "$0")" && pwd); RUN=${1:-run1}; ulimit -n 100000
S=$HOME/s4-b9-bt-logs/$RUN/chain.status; mkdir -p "$(dirname "$S")"; echo "chain start $(date -u +%FT%TZ)" >> "$S"
ARMS="10:65535 10:10 10:1000 50:65535 50:10 50:1000 200:65535 200:10 200:1000"
[ "${2:-}" = first ] && ARMS="10:65535"
for a in $ARMS; do
  python3 "$H/cluster-run.py" "$RUN" "${a%%:*}" "${a##*:}" > "$HOME/s4-b9-bt-logs/$RUN/chain-${a/:/-}.out" 2>&1; rc=$?
  echo "arm $a rc=$rc $(date -u +%FT%TZ)" >> "$S"
  if [ $rc -ne 0 ]; then echo "STOP: arm $a failed" >> "$S"; break; fi
done
python3 "$H/cluster-run.py" "$RUN" down >> "$S" 2>&1
echo "chain done $(date -u +%FT%TZ)" >> "$S"
