#!/usr/bin/env bash
# ss.sh <pid> <outdir>: every 2 s, server-side (sport 9042) established count, sum/max Send-Q, and client-side sum Recv-Q.
P=$1 R=$2
echo "epoch_ms,srv_conns,srv_sendq_sum,srv_sendq_max,cli_recvq_sum" > "$R/ss.csv"
while kill -0 $P 2>/dev/null; do
  t=$(date +%s%3N)
  s=$(ss -tnH state established '( sport = :9042 )' 2>/dev/null | awk '{n++; s+=$2; if ($2>m) m=$2} END {printf "%d,%d,%d", n, s, m}')
  c=$(ss -tnH state established '( dport = :9042 )' 2>/dev/null | awk '{s+=$1} END {printf "%d", s}')
  echo "$t,$s,$c" >> "$R/ss.csv"; sleep 2
done
