#!/usr/bin/env bash
# Stage-4 cluster tier (B3 as amended D1-1, D1-2, D1-4..D1-6; harness fix D3-1 for attempt 2) for
# dfs.datanode.du.reserved-append-getAvailable--autonomous (queue order 28, Jingsong). Runs on pc72.
# Usage: cluster-run.sh all|stop|teardown
#   all:      B3e steps 1-7 (fresh ext2 image, NN + DN, seed 122 files, boundary -4/+4 MiB, control R=0,
#             fill a=48 MiB, fill a=80 MiB); daemons stopped at the end (EXIT trap), image left mounted
#   stop:     stop daemons of this run (idempotent)
#   teardown: stop daemons, unmount and delete the image and bulk data (keeps logs and CSVs)
# Every command and its output is logged to $LOGS/cluster-run.log (append); readings per append go to
# $LOGS/readings.csv.
set -uo pipefail
MODE=${1:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-append-getAvailable-run1
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
MIB=1048576
NEED=15728640            # B - L
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_PID_DIR=$RUN/pids HADOOP_LOG_DIR=$RUN/logs
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
CSV=$LOGS/readings.csv
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
# attempt-2 fix (D3-1): grep -c prints 0 itself on no match; never echo a second 0
cnt() { local f; f=$(dnlog); if [ -f "$f" ]; then grep -c "$1" "$f" || true; else echo 0; fi; }
# DataNode registered and has sent a block report in the last 60 s (BPServiceActor.java:199-205)
bpready() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | python3 -I -c '
import json,sys
b=json.load(sys.stdin)["beans"][0]; a=json.loads(b["BPServiceActorInfo"])
print("yes" if a and all(x["ActorState"]=="RUNNING" and int(x["LastBlockReport"])<60 for x in a) else "no")' 2>/dev/null; }
# VolumeInfo: freeSpace usedSpace reservedSpace reservedSpaceForReplicas numBlocks
vinfo() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | python3 -I -c '
import json,sys
b=json.load(sys.stdin)["beans"][0]; v=list(json.loads(b["VolumeInfo"]).values())[0]
print(v["freeSpace"], v["usedSpace"], v["reservedSpace"], v["reservedSpaceForReplicas"], v["numBlocks"])' 2>/dev/null; }
dub() { du -sb "$RUN/mnt/dn" 2>/dev/null | cut -f1; }
dfm() { df -B1 --output=size,used,avail "$RUN/mnt" | tail -1; }
dfc() { df -B1 --output=size,used,avail "$RUN/mnt" | tail -1 | awk '{print $1","$2","$3}'; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 2
  local left; left=$(ps -u "$(id -un)" -o pid=,args= | awk -v r="$RUN" 'index($0,r) && /proc_(namenode|datanode)/ && !/awk/ {print $1}')
  if [ -n "$left" ]; then echo "  WARN: daemons left: $left"; else echo "  no NameNode/DataNode of this run"; fi; }
die() { echo "STOP: $*  [$(date '+%T')]"; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
write_conf() {  # $1 = R
  { echo '<?xml version="1.0"?><configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$RUN/tmp"
    prop fs.du.interval 5000
    prop fs.getspaceused.jitterMillis 0
    echo '</configuration>'; } > "$RUN/conf/core-site.xml"
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.namenode.name.dir "$RUN/nn"
    prop dfs.datanode.data.dir "$RUN/mnt/dn"
    prop dfs.replication 1
    prop dfs.blocksize 16m
    prop dfs.datanode.cached-dfsused.check.interval.ms 0
    prop dfs.datanode.du.reserved "$1"
    prop dfs.datanode.scan.period.hours -1
    echo '</configuration>'; } > "$RUN/conf/hdfs-site.xml"
}
# restart the DataNode with reserve $1; wait until it serves /t/fA and VolumeInfo shows reservedSpace == R
dn_restart() {
  local R=$1 i v
  echo "--- DN restart with R=$R  [$(date '+%T')]"
  hdfs --daemon stop datanode 2>/dev/null; sleep 2
  write_conf "$R"; grep du.reserved "$RUN/conf/hdfs-site.xml"
  run hdfs --daemon start datanode || die "dn start"
  for i in $(seq 1 60); do v=$(vinfo); set -- $v; [ "${3:-x}" = "$R" ] && break; sleep 1; done
  [ "${3:-x}" = "$R" ] || die "VolumeInfo reservedSpace != R ($v)"
  for i in $(seq 1 90); do [ "$(bpready)" = yes ] && break; sleep 1; done
  [ "$(bpready)" = yes ] || die "DN not registered / no block report"
  sleep 3
  echo "  DN up: VolumeInfo free/used/res/rfr/nblk = $(vinfo)"
}
# one append: label file  -> appends a CSV row, returns the append's exit code
append_one() {
  local L=$1 F=$2 B4 A4 rc ins0 ins1 app0 app1 t0 t1
  B4=$(vinfo); ins0=$(cnt 'Insufficient space for appending to'); app0=$(cnt 'Appending to')
  local du0; du0=$(dub)
  t0=$(date '+%T'); timeout 180 hdfs dfs -appendToFile "$RUN/c1m.bin" "$F" > "$LOGS/append-last.out" 2>&1; rc=$?; t1=$(date '+%T')
  [ $rc -ne 0 ] && { echo "  append $F rc=$rc:"; grep -vE '^\s+at ' "$LOGS/append-last.out" | head -5; cat "$LOGS/append-last.out" >> "$LOGS/append-errors.txt"; }
  sleep 1
  A4=$(vinfo); ins1=$(cnt 'Insufficient space for appending to'); app1=$(cnt 'Appending to')
  set -- $B4; local fb=$1 ub=$2 rs=$3 rfb=$4
  set -- $A4; local fa=$1 ua=$2 rfa=$4
  echo "$L,$F,$t0,$t1,$rc,$rs,$fb,$ub,$rfb,$fa,$ua,$rfa,$du0,$(dub),$(dfc),$((ins1-ins0)),$((app1-app0))" >> "$CSV"
  echo "  $L $F rc=$rc R=$rs free_before=$fb used_before=$ub -> free_after=$fa used_after=$ua du=$(dub) insuff+=$((ins1-ins0)) attempts+=$((app1-app0))  [$t0-$t1]"
  return $rc
}
state() { echo "  STATE $1: VolumeInfo(free used res rfr nblk)=$(vinfo) du_dn=$(dub) df(size used avail)=$(dfm)"; }
fsck_len() { hdfs fsck "$1" -files -blocks 2>/dev/null | grep -E "^$1 [0-9]+ bytes|blk_" | head -3; }
recover() { run hdfs debug recoverLease -path "$1" -retries 5; }

case "$MODE" in
stop) stopall; exit 0 ;;
teardown)
  stopall
  if mountpoint -q "$RUN/mnt"; then run rm -rf "$RUN/mnt/dn"; run sudo umount "$RUN/mnt"; fi
  run rm -rf "$RUN/vol.img" "$RUN/nn" "$RUN/tmp" "$RUN/hadoop" "$RUN/seed" "$RUN/c1m.bin" "$RUN/mnt"
  losetup -a | grep "$RUN" || echo "  no loop device on the run image"
  run du -sh "$RUNDIR"; exit 0 ;;
all) ;;
*) die "unknown mode" ;;
esac

trap 'echo "--- EXIT trap: stopping daemons [$(date +%T)]"; stopall' EXIT
echo "=== cluster-run.sh all start $(date '+%F %T %Z') host=$(hostname)"
for p in 9000 9870 9864 9866 9867; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && die "port $p in use"; done
echo "  ports 9000 9870 9864 9866 9867 free"
# ---- step 1: image, distribution, configs, format, start
if mountpoint -q "$RUN/mnt"; then run sudo umount "$RUN/mnt"; fi
run rm -rf "$RUN"; run mkdir -p "$RUN/mnt" "$RUN/pids" "$RUN/logs" "$RUN/seed"
run truncate -s 2G "$RUN/vol.img"
run mkfs.ext2 -q -F -m 0 "$RUN/vol.img" || die mkfs
run sudo mount -o loop "$RUN/vol.img" "$RUN/mnt" || die mount
run sudo chown "$(id -u):$(id -g)" "$RUN/mnt"
run stat -f "$RUN/mnt"
read FREE AVAIL < <(stat -f -c '%f %a' "$RUN/mnt"); [ "$FREE" = "$AVAIL" ] || die "Free != Available"
echo "  stat -f: Free == Available ($FREE)"
run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
run cp -r "$DIST/etc/hadoop" "$RUN/conf"
write_conf 0
run hadoop version | head -1
run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die format
run hdfs --daemon start namenode || die "nn start"
run hdfs --daemon start datanode || die "dn start"
run hdfs dfsadmin -safemode wait
for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
hdfs dfsadmin -report 2>/dev/null | head -12
# ---- step 2: seed (R = 0)
head -c 1048576 /dev/urandom > "$RUN/c1m.bin"; run ls -l "$RUN/c1m.bin"
for n in fA fB $(seq -f 'g%03g' 1 120); do cp "$RUN/c1m.bin" "$RUN/seed/$n"; done
run hdfs dfs -mkdir -p /t
run hdfs dfs -D dfs.blocksize=16m -D dfs.replication=1 -put "$RUN/seed/"* /t/ || die seed
echo "  seeded files: $(hdfs dfs -ls /t | grep -c '^-')"
fsck_len /t/fA; fsck_len /t/g120
sleep 10
T=$(df -B1 --output=size "$RUN/mnt" | tail -1 | tr -d ' ')
set -- $(vinfo); D=$2
echo "  CALIB T=$T D=$D"; state seeded
read DFS DFU DFA < <(dfm); echo "  nonDfs (df used - du dn) = $((DFU - $(dub)))"
echo "label,file,t0,t1,rc,R,free_before,used_before,rfr_before,free_after,used_after,rfr_after,du_before,du_after,df_size,df_used,df_avail,insufficient_lines,append_attempts" > "$CSV"
# ---- steps 3-4: boundary pair
boundary() {  # $1 label, $2 delta, $3 file
  local L=$1 DL=$2 F=$3 R U A k
  set -- $(vinfo); U=$2
  R=$((T - U - NEED - DL)); dn_restart "$R"
  for k in 1 2 3; do
    set -- $(vinfo); A=$1
    echo "  $L: R=$R freeSpace=$A target=$((NEED + DL)) diff=$((A - NEED - DL))"
    [ $((A - NEED - DL)) -le $MIB ] && [ $((NEED + DL - A)) -le $MIB ] && break
    U=$2; R=$((T - U - NEED - DL)); dn_restart "$R"
  done
  append_one "$L" "$F"; local rc=$?
  state "after-$L"; fsck_len "$F"
  [ $rc -ne 0 ] && recover "$F"
  return 0
}
boundary bM4M $((-4 * MIB)) /t/fA
sleep 6
boundary bP4M $((4 * MIB)) /t/fB
# ---- step 5: control R = 0
sleep 6
dn_restart 0
append_one ctrlR0 /t/fA; state after-ctrlR0; fsck_len /t/fA
# ---- steps 6-7: fills
NEXT=1
fill() {  # $1 label, $2 a
  local L=$1 AA=$2 R U A k n=0 rc
  sleep 6
  set -- $(vinfo); U=$2; R=$((T - U - AA)); echo "  $L: D_F=$U R_F=$R"
  dn_restart "$R"
  for k in 1 2; do
    set -- $(vinfo); A=$1; echo "  $L: start freeSpace=$A target=$AA diff=$((A - AA))"
    [ $((A - AA)) -le $MIB ] && [ $((AA - A)) -le $MIB ] && break
    U=$2; R=$((T - U - AA)); echo "  $L: recalibrate D_F=$U R_F=$R"; dn_restart "$R"
  done
  echo "  FILLSTART $L R_F=$R a=$AA freeSpace=$(vinfo | cut -d' ' -f1) du=$(dub) [$(date +%T)]"
  while :; do
    [ "$NEXT" -le 120 ] || { echo "  FILLEND $L: files exhausted without refusal after $n successes (D1-8)"; return 0; }
    local F=/t/g$(printf '%03d' "$NEXT"); NEXT=$((NEXT + 1))
    sleep 6
    append_one "$L" "$F"; rc=$?
    if [ $rc -ne 0 ]; then
      echo "  FILLEND $L: first refusal at $F after $n successes  R_F=$R [$(date +%T)]"
      state "stop-$L"; fsck_len "$F"; recover "$F"; return 0
    fi
    n=$((n + 1))
  done
}
fill fill48 $((48 * MIB))
fill fill80 $((80 * MIB))
state end
echo "  DN log totals: Insufficient=$(cnt 'Insufficient space for appending to') Appending=$(cnt 'Appending to') OutOfSpace=$(cnt 'Out of space') couldOnly=$(cnt 'could only be written to')"
echo "=== cluster-run.sh all end $(date '+%F %T %Z')"
