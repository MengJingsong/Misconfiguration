#!/usr/bin/env bash
# Stage-4 cluster tier (B3, as amended 2026-11-25) for
# dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous (queue order 25). Runs on pc75.
# Usage: cluster-run.sh all|stop|teardown
#   all:      main runs H = 256 MiB, 512 MiB (+ Control 3, then k = 4 pass), 1 GiB at k = 1;
#             Control 1 (H = 2 GiB, 64 puts); Control 2 (H = 512 MiB, additional-available-space at default)
#   stop:     stop daemons (idempotent)
#   teardown: stop daemons, delete bulk data (keeps logs and CSVs)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
MODE=${1:?mode}
STEM=dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
NN=localhost:19000
B=16777216
MIB=1048576
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_PID_DIR=$RUN/pids
export HADOOP_LOG_DIR=$RUN/logs-setup
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
jmx() { curl -s 'http://localhost:19864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' \
  | python3 -I -c 'import json,sys; b=json.load(sys.stdin)["beans"][0]; print(b["Capacity"], b["DfsUsed"], b["Remaining"])' 2>/dev/null; }
rep() { hdfs dfsadmin -report 2>/dev/null | awk -F': ' '/^Configured Capacity/{c=$2} /^DFS Used:/{u=$2} /^DFS Remaining:/{r=$2} END{split(c,a," ");split(u,b," ");split(r,d," "); print a[1], b[1], d[1]}' ; }
dfu() { df -B1 --output=used,avail "$RUN" | tail -1; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 3
  echo "+ ps check:"
  if ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | grep -q "$RUN"; then
    ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | grep "$RUN" | cut -c1-120; echo "  WARN: daemons left"
  else echo "  no NameNode/DataNode of this run"; fi; }
die() { echo "STOP: $*"; stopall; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
write_hdfs_site() {  # $1 = R, $2 = k, $3 = include additional-available-space=0 (1/0)
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.namenode.name.dir "$RUN/nn"
    prop dfs.datanode.data.dir "$RUN/dn"
    prop dfs.replication 1
    prop dfs.blocksize $B
    prop dfs.heartbeat.interval 1
    [ "$3" = 1 ] && prop dfs.datanode.round-robin-volume-choosing-policy.additional-available-space 0
    prop dfs.namenode.block-placement.min-blocks-for.write "$2"
    prop dfs.datanode.du.reserved "$1"
    prop dfs.namenode.http-address 0.0.0.0:19870
    prop dfs.datanode.address 0.0.0.0:19866
    prop dfs.datanode.http.address 0.0.0.0:19864
    prop dfs.datanode.ipc.address 0.0.0.0:19867
    echo '</configuration>'; } > "$RUN/conf/hdfs-site.xml"
}
# fresh <label> <H> <k> <aasZero>: B3e steps 1-4
fresh() {
  local L=$1 H=$2 K=$3 Z=$4
  echo "===== fresh cluster $L: H=$H k=$K aasZero=$Z  [$(date '+%T')]"
  stopall
  rm -rf "$RUN/nn" "$RUN/dn" "$RUN/tmp"
  export HADOOP_LOG_DIR=$RUN/logs-$L
  mkdir -p "$HADOOP_LOG_DIR" "$RUN/dn"
  read USED AVAIL < <(df -B1 --output=used,avail "$RUN/dn" | tail -1)
  [ "$AVAIL" -gt $((H + 2147483648)) ] || die "precondition AVAIL > H + 2 GiB"
  R=$((USED + AVAIL - H))
  echo "  df used=$USED avail=$AVAIL -> R=$R (T'=$((USED+AVAIL)))"
  write_hdfs_site "$R" "$K" "$Z"
  grep -E 'du.reserved|additional|min-blocks' "$RUN/conf/hdfs-site.xml"
  run hdfs namenode -format -force -nonInteractive > "$LOGS/format-$L.log" 2>&1 || die format
  run hdfs --daemon start namenode || die "nn start"
  run hdfs --daemon start datanode || die "dn start"
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
  sleep 3
  set -- $(rep); local CAP=$1 DU=$2 REM=$3
  local FREEUS=$(python3 -I -c "import os; s=os.statvfs('$RUN/dn'); print((s.f_bfree-s.f_bavail)*s.f_frsize)")
  echo "  START $L: report Configured=$CAP DFSUsed=$DU DFSRemaining=$REM; jmx Cap/DfsUsed/Rem=$(jmx); DF.free-DF.usable=$FREEUS"
  echo "  CHECK $L: Configured - (H + free-usable) = $((CAP - H - FREEUS)); DFSRemaining - (H - DFSUsed) = $((REM - H + DU))"
  run hdfs dfs -mkdir -p /fill
}
# putloop <label> <max puts> [<scratch-after-put>]: B3c with B3d readings; 3 consecutive failures stop it
putloop() {
  local L=$1 MAX=$2 SC=${3:-0} i ok=0 cf=0 csv="$LOGS/readings-$1.csv"
  echo "label,i,rc,ts,jmxCapacity,jmxDfsUsed,jmxRemaining,repConfigured,repDfsUsed,repRemaining,duCurrent,finalizedBytes,dfUsed,dfAvail,err" > "$csv"
  echo "--- put loop $L (max $MAX)  [$(date '+%T')]"
  for i in $(seq 1 "$MAX"); do
    hdfs dfs -put "$RUN/f16m" /fill/f$i 2>"$RUN/put.err"; rc=$?
    sleep 3
    err=$(grep -v NativeCodeLoader "$RUN/put.err" | grep -m1 -oE 'could only be written to[^.]*\.[^.]*\.|Out of space[^)]*\)|Exception[^,]*' | tr ',' ';' | head -1)
    [ $rc -ne 0 ] && grep -v NativeCodeLoader "$RUN/put.err" >> "$LOGS/put-errors-$L.txt"
    echo "$L,$i,$rc,$(date +%s),$(jmx | tr ' ' ','),$(rep | tr ' ' ','),$(du -sb "$RUN/dn/current" | cut -f1),$(find "$RUN/dn/current" -path '*finalized*' -type f -printf '%s\n' | awk '{s+=$1} END {print s+0}'),$(dfu | tr -s ' ' ',' | sed 's/^,//'),$err" >> "$csv"
    if [ $rc -eq 0 ]; then ok=$((ok+1)); cf=0; else cf=$((cf+1)); fi
    if [ "$SC" -gt 0 ] && [ "$i" -eq "$SC" ]; then control3; fi
    [ $cf -ge 3 ] && break
  done
  echo "RESULT $L: accepted=$ok attempted=$i"
  tail -4 "$csv"
}
control3() {  # B3h Control 3: 200 MiB non-HDFS file on the same filesystem
  echo "--- Control 3 at $(date '+%T')"
  sleep 3; echo "  C3 before: jmx=$(jmx) rep=$(rep) df=$(dfu)"
  mkdir -p "$RUN/scratch"
  run dd if=/dev/zero of="$RUN/scratch/c3" bs=1M count=200 conv=fsync status=none
  sleep 4; echo "  C3 after:  jmx=$(jmx) rep=$(rep) df=$(dfu)"
  sleep 3; echo "  C3 after+3s: jmx=$(jmx) rep=$(rep) df=$(dfu)"
}
greplogs() {  # $1 = label
  echo "  LOGS $1: NN NOT_ENOUGH_STORAGE_SPACE lines=$(grep -c 'NOT_ENOUGH_STORAGE_SPACE' "$(nnlog)"); distinct: $(grep -o 'Not enough replicas was chosen. Reason: {[^}]*}' "$(nnlog)" | sort | uniq -c | tr '\n' ' ')"
  echo "  LOGS $1: NN check DEBUG 'does not have enough' lines=$(grep -c 'does not have enough' "$(nnlog)") (IPC handler: $(grep 'does not have enough' "$(nnlog)" | grep -c 'IPC Server handler'))"
  grep 'does not have enough' "$(nnlog)" | head -1 | cut -c1-300
  echo "  LOGS $1: DN 'Out of space' lines=$(grep -c 'Out of space' "$(dnlog)"); 'less than the block size' lines=$(grep -c 'less than the block size' "$(dnlog)")"
  grep -m1 'Not enough replicas was chosen' "$(nnlog)" | cut -c1-250
  grep -m1 'Out of space' "$(dnlog)" | cut -c1-250
}

[ "$MODE" = all ] && trap 'echo "EXIT trap: stopping daemons"; stopall' EXIT   # instrument fix (attempt 1 left daemons after a script error)
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
case "$MODE" in
all)
  [ -e "$RUN" ] && die "$RUN exists"
  run ss -ltn | grep -E ':(19000|1986[4-7]|19870) ' && die "port in use"
  ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | cut -c1-150
  mkdir -p "$RUN"/{pids,tmp}
  run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
  run cp -r "$DIST/etc/hadoop" "$RUN/conf" || die "conf copy"
  echo 'log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG' >> "$RUN/conf/log4j.properties"  # D2-1
  { echo '<?xml version="1.0"?><configuration>'; prop fs.defaultFS hdfs://$NN; prop hadoop.tmp.dir "$RUN/tmp"; echo '</configuration>'; } > "$RUN/conf/core-site.xml"
  run cat "$RUN/conf/core-site.xml"
  run hadoop version
  echo "+ head -c 16777216 /dev/urandom > $RUN/f16m"; head -c $B /dev/urandom > "$RUN/f16m"; ls -l "$RUN/f16m"
  for HM in 256 512 1024; do
    H=$((HM * MIB)); L=H${HM}k1
    fresh $L $H 1 1
    if [ $HM = 512 ]; then putloop $L 80 10; else putloop $L 80; fi
    sleep 3; echo "  END $L: jmx=$(jmx) rep=$(rep) blk=$(find "$RUN/dn/current" -name 'blk_*' ! -name '*.meta' | wc -l)"
    greplogs $L
    if [ $HM = 512 ]; then
      run rm -rf "$RUN/scratch"
      echo "===== H512 second pass, k = 4 via reconfig  [$(date '+%T')]"
      run hdfs dfs -rm -r -skipTrash /fill
      for i in $(seq 1 60); do set -- $(jmx); [ "${2:-999999999}" -lt $MIB ] && break; sleep 2; done
      sleep 3; echo "  after rm: jmx=$(jmx) rep=$(rep)"
      write_hdfs_site "$R" 4 1
      run hdfs dfsadmin -reconfig namenode $NN start
      for i in $(seq 1 30); do s=$(hdfs dfsadmin -reconfig namenode $NN status 2>&1); echo "$s" | grep -q 'finished' && break; sleep 1; done
      echo "$s"
      grep -h 'min-blocks-for.write' "$(nnlog)" | tail -2 | cut -c1-250
      run hdfs dfs -mkdir -p /fill
      L=H512k4; putloop $L 80
      sleep 3; echo "  END $L: jmx=$(jmx) rep=$(rep)"
      greplogs H512k4-same-NN-log
    fi
  done
  fresh C1H2048 $((2048 * MIB)) 1 1; putloop C1H2048 64
  sleep 3; echo "  END C1H2048: jmx=$(jmx) rep=$(rep)"; greplogs C1H2048
  fresh C2H512aas $((512 * MIB)) 1 0
  grep -c additional-available-space "$RUN/conf/hdfs-site.xml"
  putloop C2H512aas 80
  sleep 3; echo "  END C2H512aas: jmx=$(jmx) rep=$(rep)"; greplogs C2H512aas
  stopall ;;
stop) stopall ;;
teardown)
  stopall
  for d in "$RUN"/logs-*; do [ -d "$d" ] && mkdir -p "$LOGS/daemon-logs/$(basename "$d")" && cp "$d"/*.log "$LOGS/daemon-logs/$(basename "$d")/" 2>/dev/null; done
  run rm -rf "$RUN/hadoop" "$RUN/nn" "$RUN/dn" "$RUN/tmp" "$RUN/pids" "$RUN/f16m" "$RUN/scratch" "$RUN/put.err" "$RUN"/logs-*
  run du -sh "$RUNDIR" ;;
esac
echo "=== cluster-run.sh $MODE end $(date '+%F %T %Z')"
