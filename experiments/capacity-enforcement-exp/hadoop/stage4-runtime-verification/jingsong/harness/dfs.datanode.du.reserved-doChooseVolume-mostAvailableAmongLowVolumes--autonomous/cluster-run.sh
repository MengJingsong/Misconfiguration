#!/usr/bin/env bash
# Stage-4 cluster tier (B3, as amended D1-3/D1-4/D1-5) for
# dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous (queue order 27). Runs on pc82.
# Usage: cluster-run.sh all|stop|teardown
#   all:      setup (dist copy, conf, 12 GiB ext4 loop fs at $RUN/dn), K1, K2, K3 (45 sequential puts each),
#             K1c (8 concurrent 1000 MiB writers, 3 repetitions). Re-format between runs.
#   stop:     stop daemons (idempotent)
#   teardown: stop daemons, copy daemon logs, unmount and delete the loop fs, delete bulk data (keeps logs)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
MODE=${1:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes-run1
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
IMG=$RUNDIR/dn.img
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
NN=127.0.0.1:19820
B=104857600; S=105676807; MIB=1048576; GIB=1073741824
POLICY=org.apache.hadoop.hdfs.server.datanode.fsdataset.AvailableSpaceVolumeChoosingPolicy
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_PID_DIR=$RUN/pids
export HADOOP_LOG_DIR=$RUN/logs-setup
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
# JMX VolumeInfo -> "free0 free1 res0 res1 rfr0 rfr1 used0 used1 nb0 nb1"
vinfo() { curl -s 'http://127.0.0.1:19864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | python3 -I -c '
import json,sys
d=sys.argv[1]
try:
    v=json.loads(json.load(sys.stdin)["beans"][0]["VolumeInfo"])
    a=v[d+"/d0"]; b=v[d+"/d1"]
    print(a["freeSpace"],b["freeSpace"],a["reservedSpace"],b["reservedSpace"],a["reservedSpaceForReplicas"],b["reservedSpaceForReplicas"],a["usedSpace"],b["usedSpace"],a["numBlocks"],b["numBlocks"])
except Exception as e:
    print("NA NA NA NA NA NA NA NA NA NA")' "$RUN/dn"; }
blkb() { find "$RUN/dn/$1/current" -type f -name 'blk_*' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{print s+0}'; }
finb() { find "$RUN/dn/$1/current" -path '*finalized*' -type f -name 'blk_*' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{print s+0}'; }
blkn() { find "$RUN/dn/$1/current" -type f -name 'blk_*' ! -name '*.meta' 2>/dev/null | wc -l; }
dub() { du -sb "$RUN/dn/$1" | cut -f1; }
loopavail() { df -B1 --output=avail "$RUN/dn" | tail -1 | tr -d ' '; }
mydavail() { df -B1 --output=avail /mydata | tail -1 | tr -d ' '; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 3
  local left; left=$(ps -u "$(id -un)" -o pid=,args= | awk -v r="$RUN" '/proc_namenode|proc_datanode/ && index($0, r) && !/awk/')
  if [ -n "$left" ]; then echo "$left" | cut -c1-150; echo "  WARN: daemons left, killing"; echo "$left" | awk '{print $1}' | xargs -r kill; sleep 3;
  else echo "  ps check: no NameNode/DataNode of this run"; fi; }
die() { echo "STOP: $*"; stopall; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
# write_hdfs_site <mode> <b0|global b> <b1> <threshold>; mode = perdir|global
write_hdfs_site() {
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.replication 1
    prop dfs.blocksize $B
    prop dfs.namenode.name.dir "file://$RUN/nn"
    prop dfs.datanode.data.dir "file://$RUN/dn/d0,file://$RUN/dn/d1"
    prop dfs.namenode.rpc-address $NN
    prop dfs.namenode.http-address 127.0.0.1:19870
    prop dfs.datanode.address 127.0.0.1:19866
    prop dfs.datanode.http.address 127.0.0.1:19864
    prop dfs.datanode.ipc.address 127.0.0.1:19867
    prop dfs.heartbeat.interval 1
    prop dfs.permissions.enabled false
    prop dfs.datanode.fsdataset.volume.choosing.policy $POLICY
    prop dfs.datanode.available-space-volume-choosing-policy.balanced-space-threshold "$4"
    prop dfs.datanode.available-space-volume-choosing-policy.balanced-space-preference-fraction 0.0
    if [ "$1" = perdir ]; then
      prop "dfs.datanode.du.reserved.$RUN/dn/d0" "$((TOTAL - ROOTRES - $2))"
      prop "dfs.datanode.du.reserved.$RUN/dn/d1" "$((TOTAL - ROOTRES - $3))"
    else
      prop dfs.datanode.du.reserved "$((TOTAL - ROOTRES - $2))"
    fi
    echo '</configuration>'; } > "$RUN/conf/hdfs-site.xml"
}
# fresh <label> <mode> <b0> <b1> <threshold>: B3e steps 1-3 (re-format, start, check knob landed)
fresh() {
  local L=$1
  echo "===== fresh cluster $L: mode=$2 b0=$3 b1=$4 T=$5  [$(date '+%F %T %Z')]"
  stopall
  rm -rf "$RUN/nn" "$RUN/tmp" "$RUN/dn/d0" "$RUN/dn/d1"
  mkdir -p "$RUN/nn" "$RUN/tmp" "$RUN/dn/d0" "$RUN/dn/d1"
  export HADOOP_LOG_DIR=$RUN/logs-$L
  mkdir -p "$HADOOP_LOG_DIR"
  read TOTAL ROOTRES < <(python3 -I -c 'import os,sys;s=os.statvfs(sys.argv[1]);print(s.f_blocks*s.f_frsize,(s.f_bfree-s.f_bavail)*s.f_frsize)' "$RUN/dn")
  echo "  TOTAL=$TOTAL ROOTRES=$ROOTRES loopAvail=$(loopavail) mydataAvail=$(mydavail)"
  [ "$(loopavail)" -ge $((10 * GIB)) ] || die "loop fs usable < 10 GiB (B3a)"
  write_hdfs_site "$2" "$3" "$4" "$5"
  grep -E 'du.reserved|balanced|choosing.policy' "$RUN/conf/hdfs-site.xml"
  run hdfs namenode -format -force -nonInteractive > "$LOGS/format-$L.log" 2>&1 || die format
  run hdfs --daemon start namenode || die "nn start"
  run hdfs --daemon start datanode || die "dn start"
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
  sleep 3
  local V; V=$(vinfo)
  echo "  START $L: VolumeInfo free0 free1 res0 res1 rfr0 rfr1 used0 used1 nb0 nb1 = $V"
  echo "$L,$TOTAL,$ROOTRES,$(echo $V | tr ' ' ',')" >> "$LOGS/start-checks.csv"
}
# check_start <label> <R0 expected> <R1 expected> <b0> <b1>: B3e step 3
check_start() {
  set -- "$1" "$2" "$3" "$4" "$5" $(vinfo)
  local L=$1 ER0=$2 ER1=$3 EB0=$4 EB1=$5 F0=$6 F1=$7 R0=$8 R1=$9
  echo "  CHECK $L: reserved0-R0=$((R0 - ER0)) reserved1-R1=$((R1 - ER1)) b0-free0=$((EB0 - F0)) b1-free1=$((EB1 - F1))"
  [ "$R0" = "$ER0" ] && [ "$R1" = "$ER1" ] || die "reservedSpace != R_i (knob did not land)"
  [ $((EB0 - F0)) -ge 0 ] && [ $((EB0 - F0)) -le $MIB ] && [ $((EB1 - F1)) -ge 0 ] && [ $((EB1 - F1)) -le $MIB ] || die "freeSpace not within 1 MiB of b_i"
}
# putloop <label> <n>: B3c sequential with B3d readings after each put
putloop() {
  local L=$1 N=$2 i ok=0 csv="$LOGS/readings-$1.csv"
  echo "label,i,rc,ts,blk0,blk1,fin0,fin1,cnt0,cnt1,du0,du1,free0,free1,res0,res1,rfr0,rfr1,used0,used1,nb0,nb1,dnDebug,nnRefusals,dnOutOfSpace,loopAvail,mydataAvail,err" > "$csv"
  echo "--- put loop $L (n=$N)  [$(date '+%T')]"
  run hdfs dfs -mkdir -p /t /c
  for i in $(seq 1 "$N"); do
    local dn0 nn0; dn0=$(wc -l < "$(dnlog)"); nn0=$(wc -l < "$(nnlog)")
    timeout 300 hdfs dfs -put "$RUN/src/f100m" /t/f$i 2>"$RUN/put.err"; rc=$?
    echo "$i $rc"
    sleep 3
    local dbg nnr oos err
    dbg=$(tail -n +$((dn0 + 1)) "$(dnlog)" | grep -oE 'Selecting [^ ]+ from (high|low) available space volumes|All volumes are within[^.]*\. Selecting [^ ]+' | sed -e "s#$RUN/dn/##g" -e 's/ available space volumes//' -e 's/All volumes are within.*Selecting /balanced:/' -e 's/Selecting //' | tr '\n' ';')
    nnr=$(tail -n +$((nn0 + 1)) "$(nnlog)" | grep -c 'does not have enough')
    oos=$(tail -n +$((dn0 + 1)) "$(dnlog)" | grep -c 'Out of space')
    err=$(grep -v NativeCodeLoader "$RUN/put.err" | grep -m1 -oE 'could only be written to[^.]*\.|Out of space[^)]*\)|[A-Za-z.]*Exception[^,]*' | tr ',' ';' | head -1)
    [ $rc -ne 0 ] && { echo "--- put $i:"; grep -v NativeCodeLoader "$RUN/put.err"; } >> "$LOGS/put-errors-$L.txt"
    echo "$L,$i,$rc,$(date +%s),$(blkb d0),$(blkb d1),$(finb d0),$(finb d1),$(blkn d0),$(blkn d1),$(dub d0),$(dub d1),$(vinfo | tr ' ' ','),$dbg,$nnr,$oos,$(loopavail),$(mydavail),$err" >> "$csv"
    [ $rc -eq 0 ] && ok=$((ok+1))
    [ "$(mydavail)" -ge $((6 * GIB)) ] || die "/mydata usable < 6 GiB (B4)"
  done
  echo "RESULT $L: accepted=$ok of $N; final blk0=$(blkb d0) blk1=$(blkb d1) cnt=$(blkn d0)/$(blkn d1) vinfo=$(vinfo)"
}
greplogs() {
  echo "  LOGS $1: DN DEBUG imbalanced-high=$(grep -c 'from high available space' "$(dnlog)") imbalanced-low=$(grep -c 'from low available space' "$(dnlog)") balanced=$(grep -c 'All volumes are within' "$(dnlog)") 'Out of space'=$(grep -c 'Out of space' "$(dnlog)") 'less than the block size'=$(grep -c 'less than the block size' "$(dnlog)")"
  echo "  LOGS $1: NN 'does not have enough' lines=$(grep -c 'does not have enough' "$(nnlog)"); reasons: $(grep -o 'Not enough replicas was chosen. Reason: {[^}]*}' "$(nnlog)" | sort | uniq -c | tr '\n' ' ')"
  grep -m1 'does not have enough' "$(nnlog)" | cut -c1-300
  grep -m1 'Out of space' "$(dnlog)" | cut -c1-300
}
# k1c <rep>: B3c K1c, 8 concurrent writers of 1000 MiB, sampled every 2 s
k1c() {
  local L=K1c-$1 csv="$LOGS/readings-K1c-$1.csv" w
  fresh "$L" perdir $GIB $((3 * GIB)) $MIB
  check_start "$L" $((TOTAL - ROOTRES - GIB)) $((TOTAL - ROOTRES - 3 * GIB)) $GIB $((3 * GIB))
  run hdfs dfs -mkdir -p /c
  echo "ts,blk0,blk1,fin0,fin1,free0,free1,res0,res1,rfr0,rfr1,used0,used1,nb0,nb1,writersAlive" > "$csv"
  local pids=()
  for w in 1 2 3 4 5 6 7 8; do timeout 900 hdfs dfs -put "$RUN/src/f1000m" /c/w$w 2>"$RUN/k1c-w$w.err" & pids+=($!); done
  while :; do
    local alive=0; for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive+1)); done
    echo "$(date +%s),$(blkb d0),$(blkb d1),$(finb d0),$(finb d1),$(vinfo | tr ' ' ','),$alive" >> "$csv"
    [ $alive -eq 0 ] && break
    sleep 2
  done
  for w in 1 2 3 4 5 6 7 8; do wait "${pids[$((w-1))]}"; echo "  writer w$w rc=$?"; { echo "--- w$w:"; grep -v NativeCodeLoader "$RUN/k1c-w$w.err"; } >> "$LOGS/put-errors-$L.txt"; done
  sleep 5
  echo "$(date +%s),$(blkb d0),$(blkb d1),$(finb d0),$(finb d1),$(vinfo | tr ' ' ','),final" >> "$csv"
  local b0=$(blkb d0) b1=$(blkb d1)
  echo "RESULT $L: blk0=$b0 blk1=$b1 over0=$((b0 > GIB ? b0 - GIB : 0)) over1=$((b1 > 3 * GIB ? b1 - 3 * GIB : 0)) S=$S cnt=$(blkn d0)/$(blkn d1) fin=$(finb d0)/$(finb d1) vinfo=$(vinfo)"
  run hdfs dfs -ls /c
  greplogs "$L"
}

[ "$MODE" = all ] && trap 'echo "EXIT trap: stopping daemons"; stopall' EXIT
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
case "$MODE" in
all)
  [ -e "$RUN" ] && die "$RUN exists"
  ss -ltn | grep -E ':(19820|19870|19864|19866|19867) ' && die "port in use"
  mkdir -p "$RUN"/{pids,tmp,src,dn}
  run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
  run rm -rf "$RUN/conf"; run cp -r "$DIST/etc/hadoop" "$RUN/conf" || die "conf copy"
  { echo "log4j.logger.$POLICY=DEBUG"
    echo 'log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.BlockPlacementPolicy=DEBUG'; } >> "$RUN/conf/log4j.properties"  # B3a + D1-4
  { echo '<?xml version="1.0"?><configuration>'; prop fs.defaultFS hdfs://$NN; prop hadoop.tmp.dir "$RUN/tmp"; echo '</configuration>'; } > "$RUN/conf/core-site.xml"
  { echo "export JAVA_HOME=$JAVA_HOME"; echo "export HADOOP_PID_DIR=$RUN/pids"; echo "export HADOOP_HEAPSIZE_MAX=1g"; } >> "$RUN/conf/hadoop-env.sh"
  run cat "$RUN/conf/core-site.xml"
  run hadoop version
  # D1-3: 12 GiB ext4 loop file system for the two data directories
  run truncate -s 12G "$IMG" || die truncate
  run mkfs.ext4 -q -F "$IMG" || die mkfs
  run sudo mount -o loop "$IMG" "$RUN/dn" || die mount
  run sudo chown "$(id -un)" "$RUN/dn"
  run findmnt -no SOURCE,FSTYPE,SIZE,AVAIL "$RUN/dn"
  losetup -j "$IMG" | tee "$LOGS/losetup.txt"
  echo "+ head -c $B /dev/urandom > $RUN/src/f100m"; head -c $B /dev/urandom > "$RUN/src/f100m"
  echo "+ head -c 1048576000 /dev/urandom > $RUN/src/f1000m"; head -c 1048576000 /dev/urandom > "$RUN/src/f1000m"
  ls -l "$RUN/src"
  run df -B1 "$RUN/dn" /mydata
  # K1
  fresh K1 perdir $GIB $((3 * GIB)) $MIB
  check_start K1 $((TOTAL - ROOTRES - GIB)) $((TOTAL - ROOTRES - 3 * GIB)) $GIB $((3 * GIB))
  putloop K1 45; greplogs K1
  # K2
  fresh K2 perdir 536870912 2147483648 $MIB
  check_start K2 $((TOTAL - ROOTRES - 536870912)) $((TOTAL - ROOTRES - 2147483648)) 536870912 2147483648
  putloop K2 45; greplogs K2
  # K3 (no-166 control): global key, threshold 10 GiB
  fresh K3 global $GIB 0 10737418240
  check_start K3 $((TOTAL - ROOTRES - GIB)) $((TOTAL - ROOTRES - GIB)) $GIB $GIB
  putloop K3 45; greplogs K3
  # K1c x3
  for rep in 1 2 3; do k1c $rep; done
  stopall
  run df -B1 "$RUN/dn" /mydata ;;
stop) stopall ;;
teardown)
  stopall
  for d in "$RUN"/logs-*; do [ -d "$d" ] && mkdir -p "$LOGS/daemon-logs/$(basename "$d")" && cp "$d"/*.log "$LOGS/daemon-logs/$(basename "$d")/" 2>/dev/null; done
  cp "$RUN/conf/hdfs-site.xml" "$RUN/conf/core-site.xml" "$LOGS/" 2>/dev/null
  if findmnt -n "$RUN/dn" >/dev/null; then run sudo umount "$RUN/dn"; fi
  run losetup -j "$IMG"
  run rm -f "$IMG"
  run rm -rf "$RUN/hadoop" "$RUN/nn" "$RUN/dn" "$RUN/tmp" "$RUN/pids" "$RUN/src" "$RUN/put.err" "$RUN"/k1c-w*.err "$RUN"/logs-* "$RUN/conf"
  run du -sh "$RUNDIR" ;;
esac
echo "=== cluster-run.sh $MODE end $(date '+%F %T %Z')"
