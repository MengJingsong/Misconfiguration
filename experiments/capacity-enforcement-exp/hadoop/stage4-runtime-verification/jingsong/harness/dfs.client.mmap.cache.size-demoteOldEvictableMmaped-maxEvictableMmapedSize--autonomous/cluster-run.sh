#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A6-A8) for dfs.client.mmap.cache.size-...--autonomous. Runs on pc91.
# Usage: cluster-run.sh <harness-dir> setup|run|stop
#   setup: dist copy + libhadoop, configs, checknative, format, start NN+DN, load 1 GiB, compile probe, -cat baseline
#   run:   every probe run of B3b/B3h (+A7 repeats and JDK 11 client runs); then stop daemons
#   stop:  stop daemons (idempotent) + ps check
# Every command and its output -> $LOGS/cluster-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
R=$RUNDIR/cluster
SOCK=/mydata/jingsong-s4/o12-sock
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
J8=/usr/lib/jvm/java-8-openjdk-amd64; J11=/usr/lib/jvm/java-11-openjdk-amd64
export JAVA_HOME=$J8
export HADOOP_HOME=$R/hadoop-3.4.2 HADOOP_CONF_DIR=$R/conf HADOOP_LOG_DIR=$R/logs HADOOP_PID_DIR=$R/pids
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$J8/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS" "$R/out"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
die() { echo "STOP: $*"; exit 1; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
stopall() {
  hdfs --daemon stop datanode; hdfs --daemon stop namenode; sleep 3
  echo "+ ps check:"; ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode|[M]mapCapProbe' | cut -c1-160 || echo "  no NameNode/DataNode/probe process"
}
# probe <tag> <java_home> <extra -D args...>
probe() {
  local tag=$1 jh=$2; shift 2
  local out=$R/out/$tag.log ext=$R/out/$tag.ext
  echo "--- probe $tag (JAVA_HOME=$jh) args: $*"
  echo "+ JAVA_HOME=$jh HADOOP_CLIENT_OPTS=-Xmx512m hadoop jar $R/probe/probe.jar MmapCapProbe $* /mmapcap/f16 30  [$(date '+%F %T')]"
  JAVA_HOME=$jh HADOOP_CLIENT_OPTS="-Xmx512m" hadoop jar "$R/probe/probe.jar" MmapCapProbe "$@" /mmapcap/f16 30 > "$out" 2>&1 &
  local pid=$!
  for i in $(seq 1 300); do grep -q '^after-close ' "$out" && break; kill -0 $pid 2>/dev/null || break; sleep 0.5; done
  sleep 5
  { echo "external check at $(date '+%F %T') pid=$pid cmd=$(tr '\0' ' ' < /proc/$pid/cmdline | grep -o 'MmapCapProbe' | head -1)"
    echo "blk_ data maps: $(grep -c '/blk_[0-9]*$' /proc/$pid/maps)"
    grep -E 'VmSize|RssFile' /proc/$pid/status
    pmap -x $pid | grep blk_ ; } > "$ext" 2>&1
  wait $pid; local rc=$?
  echo "  probe rc=$rc"
  grep -E '^(conf|before|after-close|end) ' "$out"
  grep -E '^step ' "$out" | awk '{print "  " $1, $2, $4, $5}' | tr '\n' ';'; echo
  echo "  disallow counts before after-close: demoteNeed=$(sed '/^after-close /q' "$out" | grep -c 'demoteOldEvictable: demoting .*because we need more space') demoteOld=$(grep -c "demoteOldEvictable: demoting .*because it's too old" "$out") purge=$(sed '/^after-close /q' "$out" | grep -c 'trimEvictionMaps is purging')"
  echo "  demoteOld total (whole run incl. hold)=$(grep -c "because it's too old" "$out") purge total=$(grep -c 'trimEvictionMaps is purging' "$out")"
  cat "$ext" | sed 's/^/  ext: /'
}

case "$MODE" in
setup)
  [ -x "$DIST/bin/hadoop" ] || die "no base dist"
  NL=$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib
  [ -e "$NL/libhadoop.so.1.0.0" ] || die "no native lib (prep.sh)"
  rm -rf "$R/hadoop-3.4.2" "$R/conf" "$R/nn" "$R/dn" "$R/tmp" "$R/logs" "$R/pids" "$R/data" "$R/probe"
  mkdir -p "$R"/{logs,pids,tmp,data,probe/classes}
  run cp -a "$DIST" "$R/hadoop-3.4.2" || die "dist copy"
  run mkdir -p "$R/hadoop-3.4.2/lib/native"
  run cp -a "$NL"/libhadoop.so* "$R/hadoop-3.4.2/lib/native/" || die "copy native"
  run cp -r "$R/hadoop-3.4.2/etc/hadoop" "$R/conf"
  mkdir -p "$SOCK"; chmod 755 "$R" "$SOCK"; run namei -l "$SOCK"
  { echo '<?xml version="1.0"?><configuration>'; prop fs.defaultFS hdfs://localhost:9000; prop hadoop.tmp.dir "$R/tmp"; echo '</configuration>'; } > "$R/conf/core-site.xml"
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.replication 1; prop dfs.namenode.name.dir "$R/nn"; prop dfs.datanode.data.dir "$R/dn"
    prop dfs.blocksize 67108864; prop dfs.domain.socket.path "$SOCK/dn_socket"
    prop dfs.client.read.shortcircuit true; prop dfs.client.read.shortcircuit.skip.checksum true
    prop dfs.client.mmap.enabled true; prop dfs.client.mmap.cache.timeout.ms 3600000
    prop dfs.client.read.shortcircuit.streams.cache.size 256; prop dfs.client.short.circuit.num 1
    prop dfs.datanode.max.locked.memory 0
    echo '</configuration>'; } > "$R/conf/hdfs-site.xml"
  echo 'log4j.logger.org.apache.hadoop.hdfs.shortcircuit.ShortCircuitCache=TRACE' >> "$R/conf/log4j.properties"
  run cat "$R/conf/core-site.xml" "$R/conf/hdfs-site.xml"; run tail -2 "$R/conf/log4j.properties"
  run hadoop version
  cn=$(hadoop checknative -a 2>&1); echo "$cn"   # checknative exits 1 when an optional lib (zstd, bzip2) is absent (defect D-1)
  echo "$cn" | grep -qE '^hadoop: +true' || die "libhadoop not loaded"
  run ss -ltn
  ss -ltn | grep -E ':(9000|9870|9864|9866|9867) ' && die "port busy"
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die "format"
  run hdfs --daemon start namenode || die "nn"
  run hdfs --daemon start datanode || die "dn"
  ok=0; for i in $(seq 1 60); do n=$(hdfs dfsadmin -report 2>/dev/null | grep -oE 'Live datanodes \([0-9]+\)' | grep -oE '[0-9]+'); [ "${n:-0}" = 1 ] && { ok=1; break; }; sleep 2; done
  [ $ok = 1 ] || die "no live datanode"
  run hdfs dfsadmin -report
  run jps
  grep -iE 'domain ?socket|dn_socket' "$R"/logs/*datanode*.log | head -5
  grep -iE 'ERROR' "$R"/logs/*datanode*.log | head -5
  run bash -c "head -c 1073741824 /dev/urandom > $R/data/f16.bin"
  run hdfs dfs -mkdir -p /mmapcap
  run hdfs dfs -D dfs.blocksize=67108864 -put "$R/data/f16.bin" /mmapcap/f16 || die "put"
  run hdfs fsck /mmapcap/f16 -blocks
  hdfs fsck /mmapcap/f16 -blocks | grep -q 'Total blocks (validated):.*16 ' || die "not 16 blocks"
  run cp "$H/MmapCapProbe.java" "$R/probe/"
  run javac -cp "$(hadoop classpath)" -d "$R/probe/classes" "$R/probe/MmapCapProbe.java" || die "javac"
  run jar cf "$R/probe/probe.jar" -C "$R/probe/classes" .
  # B3e step 5: -cat baseline, sampling the client JVM's blk_ mappings every 0.2 s
  echo "+ baseline: hdfs dfs -cat /mmapcap/f16 > /dev/null (sampling)  [$(date '+%F %T')]"
  hdfs dfs -cat /mmapcap/f16 > /dev/null 2> "$R/out/cat-baseline.err" & cp=$!
  mx=0; ns=0; while kill -0 $cp 2>/dev/null; do c=$(grep -c '/blk_[0-9]*$' /proc/$cp/maps 2>/dev/null); ns=$((ns+1)); [ "${c:-0}" -gt $mx ] && mx=$c; sleep 0.2; done
  wait $cp; echo "  cat rc=$? samples=$ns maxBlkMaps=$mx"
  grep -c 'REQUEST_SHORT_CIRCUIT_FDS' "$R"/logs/*datanode*.log | sed 's/^/  DN REQUEST_SHORT_CIRCUIT_FDS lines: /'
  echo "BASELINE samples=$ns maxBlkMaps=$mx"
  ;;
run)
  for s in 0 1 2 5 9 17 256; do probe "S$s" $J8 -Ddfs.client.mmap.cache.size=$s; done
  probe posctl $J8 -Ddfs.client.mmap.cache.size=256 -Ddfs.client.read.shortcircuit.streams.cache.size=4
  probe unmapctl $J8 -Ddfs.client.mmap.cache.size=256 -Ddfs.client.mmap.cache.timeout.ms=2000
  for s in 2 9 256; do probe "S$s-rep2" $J8 -Ddfs.client.mmap.cache.size=$s; done
  for s in 5 256; do probe "S$s-jdk11" $J11 -Ddfs.client.mmap.cache.size=$s; done
  probe unmapctl-jdk11 $J11 -Ddfs.client.mmap.cache.size=256 -Ddfs.client.mmap.cache.timeout.ms=2000
  grep -c 'REQUEST_SHORT_CIRCUIT_FDS' "$R"/logs/*datanode*.log | sed 's/^/DN REQUEST_SHORT_CIRCUIT_FDS lines: /'
  stopall
  ;;
stop) stopall ;;
esac
echo "=== cluster-run.sh $MODE end $(date '+%F %T %Z')"
