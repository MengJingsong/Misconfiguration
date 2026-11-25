#!/usr/bin/env bash
# Stage-4 cluster tier, order 20: K-runs in the AM6 order. Usage: cluster-all.sh main|k6
R=/mydata/jingsong-s4/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity-run1
S=$R/harness/cluster-run.sh
mkdir -p $R/cluster
LOG=$R/cluster/cluster-all.log
go() { echo "[$(date -u +%FT%TZ)] START $*" >> $LOG; bash $S "$@" > $R/cluster/$1.out 2>&1; echo "[$(date -u +%FT%TZ)] END $1 rc=$?" >> $LOG; }
case "${1:-main}" in
  main)
    go K1 65536 true 120 1g
    go K2 8388608 true 120 1g
    go K3 67108864 true 120 1g
    go K4 268435456 true 120 1g
    go K5 unset true 250 1g
    go K0 unset false 120 1g
    ;;
  k6)
    go K6ctl 1073741824 true 750 6g
    go K6 2147483647 true 750 6g
    ;;
esac
echo "[$(date -u +%FT%TZ)] ALL-DONE $1" >> $LOG
