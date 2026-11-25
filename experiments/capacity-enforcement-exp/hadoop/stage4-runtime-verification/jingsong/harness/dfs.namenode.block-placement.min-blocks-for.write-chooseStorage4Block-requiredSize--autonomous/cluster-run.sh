#!/usr/bin/env bash
# Stage-4 cluster tier (B3, as amended 2026-11-25) for
# dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.
# Runs on pc91. Usage: cluster-run.sh <harness-dir> setup|run|stop|teardown
#   setup:    dist copy, 512 MiB loop ext2 (-m 0) at $RUN/dnfs, du.reserved R = size - 256 MiB, configs,
#             format, start NN + DN, capacity check (B3a, B3e 1-3)
#   run:      N = 1, 8, 16, 32 (live reconfig, empty /fill, put loop), step 5 (32 -> 1 without emptying),
#             step 6 (DN-side control: additional-available-space back to its 1 GiB default), stop daemons
#   stop:     stop daemons (idempotent)
#   teardown: stop daemons, unmount the loop fs, delete bulk data (keeps logs and CSVs)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
KEY=dfs.namenode.block-placement.min-blocks-for.write
NN=localhost:29820
B=4194304
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
jmx() { curl -s 'http://localhost:29864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' \
  | python3 -I -c 'import json,sys; b=json.load(sys.stdin)["beans"][0]; print(b["Capacity"], b["DfsUsed"], b["Remaining"])' 2>/dev/null; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 3
  echo "+ ps check:"
  if ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | grep -q "$RUN"; then
    ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | grep "$RUN" | cut -c1-120; echo "  WARN: daemons left"
  else echo "  no NameNode/DataNode of this run"; fi; }
die() { echo "STOP: $*"; stopall; exit 1; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"

prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
write_hdfs_site() {  # $1 = N, $2 = include additional-available-space=0 (1/0)
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.namenode.name.dir "$RUN/nn"
    prop dfs.datanode.data.dir "$RUN/dnfs/dn"
    prop dfs.replication 1
    prop dfs.blocksize $B
    prop dfs.datanode.du.reserved "$(cat "$RUN/R")"
    [ "$2" = 1 ] && prop dfs.datanode.round-robin-volume-choosing-policy.additional-available-space 0
    prop dfs.namenode.redundancy.considerLoad false
    prop dfs.heartbeat.interval 1
    prop $KEY "$1"
    prop dfs.namenode.http-address localhost:29870
    prop dfs.datanode.address localhost:29866
    prop dfs.datanode.http.address localhost:29864
    prop dfs.datanode.ipc.address localhost:29867
    prop dfs.namenode.secondary.http-address localhost:29868
    echo '</configuration>'; } > "$RUN/conf/hdfs-site.xml"
}
reconf() {  # $1 = N
  write_hdfs_site "$1" "${2:-1}"
  run hdfs dfsadmin -reconfig namenode $NN start || return 1
  for i in $(seq 1 30); do
    s=$(hdfs dfsadmin -reconfig namenode $NN status 2>&1)
    echo "$s" | grep -q 'finished' && { echo "$s"; break; }; sleep 1; done
  echo "$s" | grep -q "To: \"$1\"" || echo "$s" | grep -q "$KEY" || echo "  (no change reported for $KEY; already $1?)"
  grep -h "$KEY" "$(nnlog)" | tail -2
}
emptyfill() {
  hdfs dfs -test -d /fill && run hdfs dfs -rm -r -skipTrash /fill
  for i in $(seq 1 60); do set -- $(jmx); [ "${2:-99999999}" -lt 1048576 ] && break; sleep 2; done
  echo "  after empty: jmx Capacity DfsUsed Remaining = $(jmx)"
  run hdfs dfs -mkdir -p /fill
}
# putloop <label> <start-index>: prints K (files written) at the end; CSV per put
putloop() {
  local L=$1 i=$2 n=0 csv="$LOGS/samples-$1.csv"
  [ -f "$csv" ] || echo "label,i,rc,ts,Capacity,DfsUsed,Remaining" > "$csv"
  echo "--- put loop $L from f$i  [$(date '+%T')]"
  while :; do
    hdfs dfs -put "$RUN/blk4m" /fill/f$i 2>>"$LOGS/put-$L.err"; rc=$?
    sleep 3
    echo "$L,$i,$rc,$(date +%s),$(jmx | tr ' ' ',')" >> "$csv"
    [ $rc -ne 0 ] && break
    n=$((n+1)); i=$((i+1))
    [ $n -ge 120 ] && { echo "  STOP: 120 puts without refusal"; break; }
  done
  echo "  $L: K=$n (files written), refused at f$i"
  echo "  failure text: $(grep -m1 -o 'could only be written to [^.]*\. There are [^.]*\.' "$LOGS/put-$L.err" | tail -1)"
  NEXT=$((i+1)); KLAST=$n
}
record() {  # $1 = label
  echo "--- record $1  [$(date '+%T')]"
  hdfs dfsadmin -report 2>/dev/null | grep -E '^(Configured Capacity|DFS Used|DFS Remaining|Non DFS Used):' | head -4
  echo "  jmx Capacity DfsUsed Remaining = $(jmx)"
  echo "  du -sb dn = $(du -sb "$RUN/dnfs/dn" | cut -f1); blk files = $(find "$RUN/dnfs/dn" -name 'blk_*' ! -name '*.meta' | wc -l)"
  echo "  df loop fs: $(df -B1 --output=size,used,avail "$RUN/dnfs" | tail -1)"
  echo "  NN DEBUG 'does not have enough' lines so far: $(grep -c 'does not have enough' "$(nnlog)")"
  grep 'does not have enough' "$(nnlog)" | tail -1 | cut -c1-260
  echo "  NN 'Not enough replicas' reasons so far: $(grep -o 'Not enough replicas was chosen. Reason: {[^}]*}' "$(nnlog)" | sort | uniq -c | tr '\n' ' ')"
  echo "  DN out-of-space lines so far: $(grep -cE 'Out of space|less than the block size' "$(dnlog)")"
}

case "$MODE" in
setup)
  [ -e "$RUN" ] && die "$RUN exists"
  mkdir -p "$RUN"/{logs,pids,tmp,dnfs}
  run ss -ltn | grep -E ':(29820|2986[4-8]|29870) ' && die "port in use"
  run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
  run cp -r "$DIST/etc/hadoop" "$RUN/conf" || die "conf copy"
  echo 'log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG' >> "$RUN/conf/log4j.properties"
  run truncate -s 512M "$RUN/vol.img"
  run mkfs.ext2 -F -q -m 0 "$RUN/vol.img" || die mkfs   # ext2: no root reserve, no ext4 delalloc reserved clusters (amendment 2026-11-25)
  run sudo mount -o loop "$RUN/vol.img" "$RUN/dnfs" || die mount
  run sudo chown "$USER" "$RUN/dnfs"
  mkdir -p "$RUN/dnfs/dn"
  run df -B1 --output=size,used,avail "$RUN/dnfs"
  run sudo tune2fs -l "$(findmnt -n -o SOURCE "$RUN/dnfs")" | grep -E 'Reserved block count|Block count|Block size'
  S=$(df -B1 --output=size "$RUN/dnfs" | tail -1 | tr -d ' '); echo $((S - 268435456)) > "$RUN/R"
  echo "loop fs size = $S; R = $(cat "$RUN/R")"
  { echo '<?xml version="1.0"?><configuration>'; prop fs.defaultFS hdfs://$NN; prop hadoop.tmp.dir "$RUN/tmp"; echo '</configuration>'; } > "$RUN/conf/core-site.xml"
  write_hdfs_site 1 1
  run cat "$RUN/conf/core-site.xml" "$RUN/conf/hdfs-site.xml"
  echo "+ head -c $B /dev/urandom > $RUN/blk4m"; head -c $B /dev/urandom > "$RUN/blk4m"; ls -l "$RUN/blk4m"
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die format
  run hdfs --daemon start namenode || die "nn start"
  run hdfs --daemon start datanode || die "dn start"
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
  sleep 3; record setup
  hdfs dfsadmin -report 2>/dev/null | grep -q '^Configured Capacity: 268435456 ' && echo "CAPACITY CHECK: OK (268435456)" || echo "CAPACITY CHECK: FAILED" ;;
run)
  echo "loop fs size R = $(cat "$RUN/R")"
  for N in 1 8 16 32; do
    echo "===== N = $N  [$(date '+%T')]"
    reconf $N || die "reconf $N"
    emptyfill
    record "N$N-before"
    putloop N$N 1
    echo "RESULT N=$N K=$KLAST"
    record "N$N-refusal"
  done
  echo "===== step 5: positive control, N 32 -> 1 without emptying  [$(date '+%T')]"
  reconf 1 || die "reconf 1"
  putloop S5 $NEXT
  echo "RESULT step5 extra=$KLAST total=$((32 + KLAST)) (if N=32 gave 32)"
  record "S5-refusal"
  echo "===== step 6: DN-side control (additional-available-space default)  [$(date '+%T')]"
  run hdfs --daemon stop datanode; sleep 3
  write_hdfs_site 1 0
  grep -c additional-available-space "$RUN/conf/hdfs-site.xml"
  run hdfs --daemon start datanode
  for i in $(seq 1 30); do set -- $(jmx); [ "${1:-0}" = 268435456 ] && break; sleep 2; done
  sleep 3
  grep 'Round robin volume choosing policy initialized' "$(dnlog)" | tail -1 | cut -c1-200
  emptyfill
  record "S6-before"
  putloop S6 1
  echo "RESULT step6 K=$KLAST"
  record "S6-refusal"
  stopall ;;
stop) stopall ;;
teardown)
  stopall
  mountpoint -q "$RUN/dnfs" && run sudo umount "$RUN/dnfs"
  mountpoint -q "$RUN/dnfs" && echo "WARN: still mounted"
  mkdir -p "$LOGS/daemon-logs"; cp "$RUN"/logs/*.log "$LOGS/daemon-logs/" 2>/dev/null
  run rm -rf "$RUN/hadoop" "$RUN/nn" "$RUN/tmp" "$RUN/pids" "$RUN/vol.img" "$RUN/blk4m" "$RUN/dnfs" "$RUN/logs"
  run du -sh "$RUNDIR" ;;
esac
echo "=== cluster-run.sh $MODE end $(date '+%F %T %Z')"
