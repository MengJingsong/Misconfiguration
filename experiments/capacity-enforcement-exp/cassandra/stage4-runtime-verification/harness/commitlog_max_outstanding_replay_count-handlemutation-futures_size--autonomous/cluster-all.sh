#!/usr/bin/env bash
# B3e.1 + B3e.3 as amended: load once, then each run twice, in the case's order.
H=$(cd "$(dirname "$0")" && pwd); SRC=/mydata/jingsong-cass-s4/o100/c509-node
BM=$SRC/build/lib/jars/byteman-4.0.20.jar; BTM=$H/slow-replay.btm
P=-Dcassandra.commitlog_max_outstanding_replay_count; PB=-Dcassandra.commitlog_max_outstanding_replay_bytes
[ "${1:-}" = noload ] || bash $H/cluster-run.sh load || exit 1
BASE="-javaagent:$BM=script:$BTM -Dcassandra.replayList=system_auth $PB=1099511627776"
for r in 1 2; do
  bash $H/cluster-run.sh replay C1024-r$r    "$BASE $P=1024"
  bash $H/cluster-run.sh replay C16384-r$r   "$BASE $P=16384"
  bash $H/cluster-run.sh replay C131072-r$r  "$BASE $P=131072"
  bash $H/cluster-run.sh replay ctlBytes-r$r "-javaagent:$BM=script:$BTM -Dcassandra.replayList=system_auth $PB=4194304 $P=131072"
  bash $H/cluster-run.sh replay ctlFast-r$r  "-Dcassandra.replayList=system_auth $PB=1099511627776 $P=131072"
  bash $H/cluster-run.sh replay ctlFull-r$r  "$P=1024"
done
echo ALL-DONE
