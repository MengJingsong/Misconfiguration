#!/usr/bin/env bash
# Cluster tier (B3, amendments A2, A5, A6, A7) for capacity-enforcement-exp Hadoop order 31 on pc91.
# Usage: cluster-run.sh all | teardown      Log: $C/logs-run/cluster-run.log (every command and its output)
set -uo pipefail
R=/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-chooseVolume-availableBytes-run1
C=$R/cluster
LR=$R/logs/cluster; mkdir -p $LR
exec > >(tee -a $LR/cluster-run.log) 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
HH=$C/hadoop
export HADOOP_CONF_DIR=$C/conf HADOOP_LOG_DIR=$C/logs HADOOP_PID_DIR=$C/pids HADOOP_HEAPSIZE_MAX=1g
DNLOG=$C/logs/hadoop-$(id -un)-datanode-$(hostname).log
MiB=1048576; BLK=16777216

run() { echo "+ [$(date +%T)] $*"; "$@"; local rc=$?; echo "  (rc=$rc)"; return $rc; }
TORN=0
die() { echo "FATAL: $*"; teardown; exit 1; }

jmx() {  # CacheCapacity CacheUsed NumBlocksCached NumBlocksFailedToCache
  curl -s --max-time 5 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' |
    python3 -I -c 'import json,sys
try:
  d=json.load(sys.stdin)["beans"][0]; print(d["CacheCapacity"],d["CacheUsed"],d["NumBlocksCached"],d["NumBlocksFailedToCache"])
except Exception: print("NA NA NA NA")'
}

write_conf() {  # $1 = comma-separated pmem dirs
  cat > $HADOOP_CONF_DIR/core-site.xml <<X
<?xml version="1.0"?>
<configuration>
<property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
<property><name>hadoop.tmp.dir</name><value>$C/tmp</value></property>
</configuration>
X
  cat > $HADOOP_CONF_DIR/hdfs-site.xml <<X
<?xml version="1.0"?>
<configuration>
<property><name>dfs.replication</name><value>1</value></property>
<property><name>dfs.namenode.name.dir</name><value>$C/nn</value></property>
<property><name>dfs.datanode.data.dir</name><value>$C/dn</value></property>
<property><name>dfs.datanode.pmem.cache.dirs</name><value>$1</value></property>
<property><name>dfs.datanode.pmem.cache.recovery</name><value>false</value></property>
<property><name>dfs.namenode.path.based.cache.refresh.interval.ms</name><value>2000</value></property>
<property><name>dfs.cachereport.intervalMsec</name><value>2000</value></property>
<property><name>dfs.heartbeat.interval</name><value>1</value></property>
</configuration>
X
  echo "conf: pmem dirs = $1"
}

dn_running() { ps -u $(id -un) -o pid=,args= | awk '/proc_datanode/ && !/awk/' | grep -q .; }
nn_running() { ps -u $(id -un) -o pid=,args= | awk '/proc_namenode/ && !/awk/' | grep -q .; }

stop_dn() {
  if dn_running; then run $HH/bin/hdfs --daemon stop datanode; fi
  for i in $(seq 1 30); do dn_running || break; sleep 1; done
  if dn_running; then echo "DataNode still running: kill -9"; ps -u $(id -un) -o pid=,args= | awk '/proc_datanode/ && !/awk/ {print $1}' | xargs -r kill -9; sleep 2; fi
  echo "DataNode stopped: $(dn_running && echo NO || echo yes)"
}

umount_all() {
  for d in $C/pmem0 $C/pmem1; do
    if mountpoint -q $d; then run sudo umount $d || { sleep 3; run sudo umount $d; }; fi
  done
  if mount | grep "$C/pmem"; then echo "a pmem tmpfs is still mounted"; return 1; fi
  echo "no pmem tmpfs mounted"
}

mount_tmpfs() {  # dir size
  mkdir -p $1; run sudo mount -t tmpfs -o size=$2,mode=1777 tmpfs $1 || die "mount $1"
  run df -B1 --output=size,used,avail,target $1
}

setup() {
  echo "== setup $(date)"
  for p in 9000 9870 9864 9866 9867 9868; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && die "port $p busy"; done
  echo "ports 9000 9870 9864 9866 9867 9868 free"
  mkdir -p $C $HADOOP_CONF_DIR $C/logs $C/pids $C/tmp $C/pmem0 $C/pmem1
  [ -d $HH ] || run cp -a /mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2 $HH || die "copy distribution"
  run cp -r $HH/etc/hadoop/. $HADOOP_CONF_DIR/ || die "copy conf"
  run $HH/bin/hadoop version
  run $HH/bin/hadoop checknative
  write_conf $C/pmem0
  echo "+ hdfs namenode -format -force -nonInteractive (log format.log)"; $HH/bin/hdfs namenode -format -force -nonInteractive > $LR/format.log 2>&1; echo "  (rc=$?)"
  run $HH/bin/hdfs --daemon start namenode
  sleep 5; nn_running || die "NameNode did not start"
  [ -f $C/in.bin ] || { echo "+ head -c 402653184 /dev/urandom > in.bin"; head -c 402653184 /dev/urandom > $C/in.bin; }
  ls -l $C/in.bin
}

# phase NAME "dir:size dir:size" FILLER(none|before|after)
phase() {
  local name=$1 spec=$2 filler=$3
  echo; echo "================ phase $name ($spec, filler=$filler) $(date)"
  if dn_running; then
    run $HH/bin/hdfs cacheadmin -removeDirectives -path /o31.bin
    sleep 5
  fi
  stop_dn
  umount_all || die "umount"
  local dirs="" sum=0 ndirs=0
  for e in $spec; do
    local d=$C/${e%%:*} s=${e#*:}
    mount_tmpfs $d $s
    dirs="${dirs:+$dirs,}$d"; ndirs=$((ndirs+1))
  done
  if [ "$filler" = before ]; then
    echo "+ [$(date +%T)] head -c 104857600 /dev/zero > pmem0/filler"; head -c 104857600 /dev/zero > $C/pmem0/filler; echo "  (rc=$?)"; run df -B1 --output=used,avail $C/pmem0
  fi
  write_conf "$dirs"
  touch $DNLOG; local off=$(wc -l < $DNLOG)
  echo "DN log offset for $name: $off"
  run $HH/bin/hdfs --daemon start datanode
  # DataNode-ready check (A5)
  local ok=0 logsum jcap nncap
  for i in $(seq 1 120); do
    sleep 1
    local added=$(tail -n +$((off+1)) $DNLOG | grep -c "Added persistent memory")
    [ "$added" -ge "$ndirs" ] || continue
    logsum=$(tail -n +$((off+1)) $DNLOG | grep "Added persistent memory" | sed 's/.*size=//' | awk '{s+=$1} END {print s}')
    jcap=$(jmx | awk '{print $1}')
    [ "$jcap" = "$logsum" ] || continue
    nncap=$($HH/bin/hdfs dfsadmin -report 2>/dev/null | awk -F': ' '/^Configured Cache Capacity/ {print $2; exit}' | awk '{print $1}')
    if [ "$nncap" = "$logsum" ]; then ok=1; break; fi
  done
  echo "DN-ready($name): ok=$ok logSum=$logsum jmxCapacity=$jcap nnConfiguredCacheCapacity=$nncap"
  [ $ok = 1 ] || die "DataNode not ready"
  tail -n +$((off+1)) $DNLOG | grep -E "Added persistent memory|Initializing cache loader|Persistent memory is used" | sed "s/^/  DNLOG /"
  if ! $HH/bin/hdfs dfs -test -e /o31.bin; then
    run $HH/bin/hdfs dfsadmin -safemode wait
    run $HH/bin/hdfs dfs -D dfs.blocksize=16777216 -put $C/in.bin /o31.bin
    run $HH/bin/hdfs fsck /o31.bin -files -blocks | grep -E "Total blocks|Total size|Status"
    run $HH/bin/hdfs cacheadmin -addPool o31pool
  fi
  if [ "$filler" = after ]; then
    echo "+ [$(date +%T)] head -c 104857600 /dev/zero > pmem0/filler"; head -c 104857600 /dev/zero > $C/pmem0/filler; echo "  (rc=$?)"; run df -B1 --output=used,avail $C/pmem0
    echo "JMX after filler: $(jmx)"
  fi
  run $HH/bin/hdfs cacheadmin -addDirective -path /o31.bin -pool o31pool -replication 1
  local t0=$(date +%s) csv=$LR/samples-$name.csv
  echo "ts,t,CacheCapacity,CacheUsed,NumBlocksCached,NumBlocksFailedToCache,du0,du1,files0,files1,dfused0,dfavail0,dfused1,dfavail1,refusals" > $csv
  local hist=() settledAt=-1 extra=0
  [ "$name" = K3 ] && extra=60
  while true; do
    local now=$(date +%s); local t=$((now-t0))
    read cap used nb nf <<< "$(jmx)"
    local du0=0 du1=0 f0=0 f1=0 u0= a0= u1= a1=
    if [ -d $C/pmem0/hdfs_pmem_cache ]; then du0=$(du -sb $C/pmem0/hdfs_pmem_cache | cut -f1); f0=$(find $C/pmem0/hdfs_pmem_cache -type f | wc -l); fi
    read u0 a0 <<< "$(df -B1 --output=used,avail $C/pmem0 | tail -1)"
    if mountpoint -q $C/pmem1; then
      [ -d $C/pmem1/hdfs_pmem_cache ] && { du1=$(du -sb $C/pmem1/hdfs_pmem_cache | cut -f1); f1=$(find $C/pmem1/hdfs_pmem_cache -type f | wc -l); }
      read u1 a1 <<< "$(df -B1 --output=used,avail $C/pmem1 | tail -1)"
    fi
    local ref=$(tail -n +$((off+1)) $DNLOG | grep -c "There is no enough persistent memory space")
    echo "$(date +%T),$t,$cap,$used,$nb,$nf,$du0,$du1,$f0,$f1,$u0,$a0,$u1,$a1,$ref" >> $csv
    hist+=("$used/$nb")
    local n=${#hist[@]}
    if [ $settledAt -lt 0 ] && [ $t -ge 90 ] && [ $n -ge 13 ]; then
      local same=1; for k in $(seq $((n-13)) $((n-1))); do [ "${hist[$k]}" = "${hist[$((n-1))]}" ] || same=0; done
      if [ $same = 1 ]; then settledAt=$t; echo "settled($name) at t=$t s: $used/$nb"; fi
    fi
    if [ $settledAt -ge 0 ] && [ $t -ge $((settledAt+extra)) ]; then break; fi
    if [ $t -ge 300 ]; then echo "settled($name)=false at t=$t"; break; fi
    sleep 5
  done
  local refAtSettle=$(awk -F, -v s=$settledAt 'NR>1 && $2<=s {r=$15} END{print r+0}' $csv)
  echo "---- final $name $(date)"
  tail -2 $csv
  run df -B1 --output=size,used,avail,target $C/pmem0 $( mountpoint -q $C/pmem1 && echo $C/pmem1 )
  run du -sb $C/pmem0/hdfs_pmem_cache $( mountpoint -q $C/pmem1 && echo $C/pmem1/hdfs_pmem_cache )
  find $C/pmem0 $( mountpoint -q $C/pmem1 && echo $C/pmem1 ) -type f -printf '%s %p\n' | sort -k2 > $LR/files-$name.txt
  awk '{s+=$1} END {print "files:", NR, "bytes:", s}' $LR/files-$name.txt
  $HH/bin/hdfs dfsadmin -report 2>/dev/null | grep -E "Cache" | sed 's/^/  NN /'
  run $HH/bin/hdfs cacheadmin -listDirectives -stats
  local L="tail -n +$((off+1)) $DNLOG"
  local cRef=$($L | grep -c "There is no enough persistent memory space")
  local cCNR=$($L | grep -c "could not reserve")
  local cFail=$($L | grep -c "Failed to cache the block")
  local cNoSp=$($L | grep -c "No space left on device")
  local cOk=$($L | grep -c "Successfully cached one replica")
  echo "refusal values ($name):"; $L | grep -o "max available space is [0-9]*, but [0-9]*is required" | sort | uniq -c
  $L | grep -E "There is no enough persistent memory space|could not reserve|Failed to cache the block|No space left" | head -4 | sed "s/^/  DNLOG /"
  $L > $LR/dnlog-$name.log
  read cap used nb nf <<< "$(jmx)"
  echo "CLCHK,$name,spec=$spec,filler=$filler,settledAt=$settledAt,logMaxBytesSum=$logsum,CacheCapacity=$cap,CacheUsed=$used,NumBlocksCached=$nb,NumBlocksFailedToCache=$nf,maxCacheUsed=$(awk -F, 'NR>1&&$4>m{m=$4}END{print m+0}' $csv),maxDu0=$(awk -F, 'NR>1&&$7>m{m=$7}END{print m+0}' $csv),maxDu1=$(awk -F, 'NR>1&&$8>m{m=$8}END{print m+0}' $csv),refusalLines=$cRef,refusalsAtSettle=$refAtSettle,couldNotReserve=$cCNR,failedToCacheBlock=$cFail,noSpaceLeft=$cNoSp,successfullyCached=$cOk"
}

teardown() {
  [ $TORN = 1 ] && return; TORN=1
  echo "== teardown $(date)"
  if dn_running; then run $HH/bin/hdfs cacheadmin -removeDirectives -path /o31.bin; sleep 3; fi
  stop_dn
  if nn_running; then run $HH/bin/hdfs --daemon stop namenode; fi
  for i in $(seq 1 30); do nn_running || break; sleep 1; done
  umount_all
  ps -u $(id -un) -o pid=,args= | awk '/proc_namenode|proc_datanode/ && !/awk/'; echo "(no daemon if empty)"
  cp -r $C/logs $LR/daemon-logs 2>/dev/null; cp $HADOOP_CONF_DIR/hdfs-site.xml $HADOOP_CONF_DIR/core-site.xml $LR/daemon-logs/ 2>/dev/null
  run rm -rf $C/nn $C/dn $C/tmp $C/in.bin $C/hadoop $C/pids
  for d in $C/pmem0 $C/pmem1; do mountpoint -q $d && echo "STILL MOUNTED $d" || rm -rf $d; done
  du -sh $R/* 2>/dev/null
  echo "== teardown done $(date)"
}

case ${1:-all} in
  all)
    setup
    phase K1 "pmem0:136m" none
    phase K2 "pmem0:264m" none
    phase K3 "pmem0:44m pmem1:204m" none
    phase K4 "pmem0:264m" after
    phase K5 "pmem0:264m" before
    teardown ;;
  teardown) teardown ;;
esac
