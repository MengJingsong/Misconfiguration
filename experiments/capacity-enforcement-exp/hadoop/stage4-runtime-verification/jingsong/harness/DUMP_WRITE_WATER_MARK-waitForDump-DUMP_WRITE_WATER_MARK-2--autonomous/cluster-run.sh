#!/usr/bin/env bash
# Cluster tier (B3, with the audit amendment of 2026-11-25) for
# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous. Runs ON the node (pc72).
# Usage: cluster-run.sh jars | setup | arm <m1|m8|m64|inf|seq> | all | teardown
# Every command and its output goes to $R/logs/cluster-run.log.
set -uo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
H=$R/hadoop
CONF=$R/conf
OUT=$R/logs/cluster
JARS=$R/jars
MNT=$R/mnt
DUMP=$R/nfs-dump
U=$(whoami)
NFSJAR=$H/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar
NBLK=4095; BS=65536; HOLD=120
MOPT="vers=3,proto=tcp,nolock,noacl,sync,wsize=65536,soft,timeo=600,retrans=2"
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$H HADOOP_CONF_DIR=$CONF
export PATH=$JAVA_HOME/bin:$H/bin:$PATH
mkdir -p "$OUT" "$R/logs"
exec > >(tee -a "$R/logs/cluster-run.log") 2>&1
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
nfspid() { jps 2>/dev/null | awk '$2=="Nfs3"{print $1}'; }
NFSLOG() { ls "$R"/logs/hadoop/hadoop-$U-nfs3-*.log 2>/dev/null | head -1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
registered() { rpcinfo -p localhost 2>/dev/null | grep -qE '100003 +3 +tcp +2049'; }

do_jars() {
  echo "=== jars $(date '+%F %T %Z')"
  mkdir -p "$JARS"; cd "$SRC" || fail "no src"
  [ -z "$(git status --short -- "$MOD/src/main")" ] || fail "main source not clean"
  run cp "$DIST/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-m1.jar"
  for v in m8 m64 inf; do
    case $v in m8) val='8L * 1024 * 1024';; m64) val='64L * 1024 * 1024';; inf) val='Long.MAX_VALUE';; esac
    run sed -i "73s/private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;/private static long DUMP_WRITE_WATER_MARK = $val;/" "$OFC"
    run sed -n 73p "$OFC"
    run git diff --stat -- "$MOD/src/main"
    run mvn -B -o -q package -pl "$MOD" -Dmaven.test.skip=true -Dmaven.javadoc.skip=true \
        > "$OUT/mvn-jar-$v.log" 2>&1 || fail "jar build $v failed"
    run cp "$SRC/$MOD/target/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-$v.jar"
    run git checkout -- "$OFC"
  done
  run git status --short -- "$MOD/src/main"
  for j in m1 m8 m64 inf; do
    echo "--- javap $j"
    javap -c -p -constants -classpath "$JARS/nfs-$j.jar" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx \
      | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1 | tee "$OUT/javap-$j.txt"
  done
  run ls -l "$JARS"
}

do_setup() {
  echo "=== setup $(date '+%F %T %Z') on $(hostname)"
  [ -d "$H" ] || run cp -a "$DIST" "$H"
  run cp "$NFSJAR" "$NFSJAR.orig"
  rm -rf "$CONF"; run cp -r "$H/etc/hadoop" "$CONF"
  mkdir -p "$R/tmp" "$R/nn" "$R/dn" "$R/pids" "$R/logs/hadoop" "$MNT"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$R/tmp"
    prop hadoop.proxyuser.$U.hosts '*'
    prop hadoop.proxyuser.$U.groups '*'
    echo '</configuration>'; } > "$CONF/core-site.xml"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.replication 1
    prop dfs.namenode.name.dir "$R/nn"
    prop dfs.datanode.data.dir "$R/dn"
    prop nfs.dump.dir "$DUMP"
    prop nfs.exports.allowed.hosts '* rw'
    prop nfs.file.dump true
    prop nfs.wtmax 1048576
    prop nfs.stream.timeout 600000
    echo '</configuration>'; } > "$CONF/hdfs-site.xml"
  cat >> "$CONF/hadoop-env.sh" <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_LOG_DIR=$R/logs/hadoop
export HADOOP_PID_DIR=$R/pids
export HDFS_NFS3_OPTS="-Xms1g -Xmx1g -XX:NativeMemoryTracking=summary"
EOF
  echo 'log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG' >> "$CONF/log4j.properties"
  run cat "$CONF/core-site.xml" "$CONF/hdfs-site.xml"
  run tail -4 "$CONF/hadoop-env.sh"; run tail -1 "$CONF/log4j.properties"
  run rpcinfo -p localhost
  run hdfs namenode -format -nonInteractive > "$OUT/nn-format.log" 2>&1 || fail "format"
  run hdfs --daemon start namenode
  run hdfs --daemon start datanode
  run hdfs dfsadmin -safemode wait
  run hdfs dfs -chmod 777 /
  run hdfs dfsadmin -report | head -12
  run jps
}

start_gateway() {
  run hdfs --daemon start nfs3
  for i in $(seq 1 30); do sleep 2; registered && break; [ -n "$(nfspid)" ] || break; done
  if ! registered; then
    echo "gateway not registered with the running portmapper; log tail:"; tail -20 "$(NFSLOG)"
    if [ ! -e "$R/pids/rpcbind-stopped" ]; then
      echo "fallback (amendment 3): stop system rpcbind for the run, start Hadoop portmap as root"
      [ -n "$(nfspid)" ] && run hdfs --daemon stop nfs3
      run sudo systemctl stop rpcbind.socket rpcbind && touch "$R/pids/rpcbind-stopped"
      run sudo -E env PATH="$PATH" HADOOP_CONF_DIR="$CONF" HADOOP_HOME="$H" JAVA_HOME="$JAVA_HOME" \
          HDFS_PORTMAP_USER=root HADOOP_PID_DIR="$R/pids" HADOOP_LOG_DIR="$R/logs/hadoop" "$H/bin/hdfs" --daemon start portmap
      sleep 5
      run hdfs --daemon start nfs3
      for i in $(seq 1 30); do sleep 2; registered && break; done
    fi
  fi
  run rpcinfo -p localhost
  run showmount -e localhost
  registered || fail "nfs3 not registered"
  echo "nfs3 pid $(nfspid)"
}

stop_gateway() {
  if mountpoint -q "$MNT"; then run sudo umount "$MNT" || run sudo umount -f -l "$MNT"; fi
  [ -n "$(nfspid)" ] && run hdfs --daemon stop nfs3
  sleep 2
  local p; p=$(nfspid); [ -n "$p" ] && { echo "nfs3 still alive, kill -9 $p"; kill -9 $p; }
  true
}

histo() {  # $1 pid $2 outfile -> prints "[B bytes, WriteCtx count"
  jcmd "$1" GC.class_histogram > "$2" 2>&1
  local b w
  b=$(awk '$4=="[B"{print $3}' "$2"); w=$(awk '$4=="org.apache.hadoop.hdfs.nfs.nfs3.WriteCtx"{print $2}' "$2")
  echo "[B_bytes=${b:-0} WriteCtx=${w:-0}"
}

do_arm() {
  local arm=$1 jar mode
  case $arm in m1|m8|m64|inf) jar=$arm; mode=ooo;; seq) jar=m1; mode=seq;; *) fail "arm $arm";; esac
  local A=$OUT/arm-$arm; mkdir -p "$A"
  echo "=== arm $arm jar=$jar mode=$mode $(date '+%F %T %Z')"
  stop_gateway
  run cp "$JARS/nfs-$jar.jar" "$NFSJAR.new"; run mv -f "$NFSJAR.new" "$NFSJAR"
  javap -c -p -constants -classpath "$NFSJAR" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1 > "$A/jar-const.txt"
  run cat "$A/jar-const.txt"
  local l0=0; [ -n "$(NFSLOG)" ] && l0=$(wc -l < "$(NFSLOG)")
  start_gateway
  local PID; PID=$(nfspid)
  run ls -la "$DUMP"
  run sudo mount -t nfs -o "$MOPT" localhost:/ "$MNT" || fail "mount"
  run grep " $MNT " /proc/mounts
  sleep 3
  echo "baseline: $(histo $PID "$A/histo-base.txt")" | tee "$A/histo-summary.txt"
  jcmd $PID GC.heap_info > "$A/heapinfo-base.txt" 2>&1
  # 1 s sampler: time, dump bytes, df avail, gateway VmRSS kB
  ( while true; do
      echo "$(date +%s.%N),$(du -sb "$DUMP" 2>/dev/null | cut -f1),$(df -B1 --output=avail "$DUMP" | tail -1 | tr -d ' '),$(awk '/VmRSS/{print $2}' /proc/$PID/status 2>/dev/null)"
      sleep 1
    done ) > "$A/samples.csv" 2>&1 &
  local SAMP=$!
  echo "sampler pid $SAMP"
  local F=t$arm
  timeout -s KILL 1200 python3 "$R/harness/oow.py" "$MNT/$F" $NBLK $BS $HOLD $mode > "$A/client.txt" 2>&1 &
  local PY=$!
  local held=no
  while kill -0 $PY 2>/dev/null; do
    if [ $held = no ] && grep -q '^HOLD ' "$A/client.txt"; then
      held=yes; echo "HOLD seen $(date '+%F %T.%N')"; sleep 60
      { echo "hold(60s): $(histo $PID "$A/histo-hold.txt")"; } | tee -a "$A/histo-summary.txt"
      jcmd $PID GC.heap_info > "$A/heapinfo-hold.txt" 2>&1
      jcmd $PID VM.native_memory summary > "$A/nmt-hold.txt" 2>&1
      { echo "dump dir at hold: $(du -sb "$DUMP" | cut -f1)"; ls -l "$DUMP"; } | tee "$A/dump-hold.txt"
      cp "$(NFSLOG)" "$A/nfs3-at-hold.log.tmp"; tail -n +$((l0 + 1)) "$A/nfs3-at-hold.log.tmp" > "$A/nfs3-at-hold.log"; rm -f "$A/nfs3-at-hold.log.tmp"
      echo "measured at $(date '+%F %T.%N')"
    fi
    sleep 1
  done
  wait $PY; local rc=$?
  echo "client exit $rc"; run cat "$A/client.txt"
  { echo "dump dir after close: $(du -sb "$DUMP" | cut -f1)"; ls -l "$DUMP"; } | tee "$A/dump-after.txt"
  sleep 5
  kill $SAMP 2>/dev/null; wait $SAMP 2>/dev/null
  local want got
  want=$(awk '/^MD5/{print $2}' "$A/client.txt")
  got=$(hdfs dfs -cat "/$F" | md5sum | cut -d' ' -f1)
  echo "md5 want=$want got=$got match=$([ "$want" = "$got" ] && echo yes || echo no)" | tee "$A/md5.txt"
  hdfs dfs -stat '%b %n' "/$F" | tee -a "$A/md5.txt"
  tail -n +$((l0 + 1)) "$(NFSLOG)" > "$A/nfs3.log"
  stop_gateway
  hdfs dfs -rm -skipTrash "/$F" > /dev/null 2>&1
  echo "=== arm $arm end $(date '+%F %T %Z')"
}

do_teardown() {
  echo "=== teardown $(date '+%F %T %Z')"
  stop_gateway
  if [ -e "$NFSJAR.orig" ]; then run cp "$NFSJAR.orig" "$NFSJAR"; fi
  if sudo $JAVA_HOME/bin/jps | awk '$2=="Portmap"' | grep -q .; then
    run sudo -E env PATH="$PATH" HADOOP_CONF_DIR="$CONF" HADOOP_HOME="$H" JAVA_HOME="$JAVA_HOME" \
        HDFS_PORTMAP_USER=root HADOOP_PID_DIR="$R/pids" HADOOP_LOG_DIR="$R/logs/hadoop" "$H/bin/hdfs" --daemon stop portmap
  fi
  if [ -e "$R/pids/rpcbind-stopped" ]; then
    run sudo systemctl start rpcbind.socket rpcbind && rm -f "$R/pids/rpcbind-stopped"
  fi
  run hdfs --daemon stop datanode
  run hdfs --daemon stop namenode
  sleep 3
  run jps; run sudo $JAVA_HOME/bin/jps
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[N]fs3|[P]ortmap|[o]ow.py' || echo "no daemon left"
  mountpoint -q "$MNT" && echo "MOUNT STILL PRESENT" || echo "mount gone"
  run systemctl is-active rpcbind
  run rpcinfo -p localhost
}

case ${1:-} in
  jars) do_jars ;;
  setup) do_setup ;;
  arm) do_arm "$2" ;;
  all) for a in m1 m8 m64 inf seq; do do_arm $a; done; echo "=== ALL ARMS DONE $(date '+%F %T %Z')" ;;
  teardown) do_teardown ;;
  *) fail "usage" ;;
esac
