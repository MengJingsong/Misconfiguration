#!/usr/bin/env bash
# Cluster tier (B3, with amendment A1 of 2026-11-25: hold 40 s < nfs.stream.timeout 60 s) for
# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous. Runs ON the node (pc82; amendments A4-A8 of 2026-11-25 applied).
# Usage: cluster-run.sh jars | setup | arm <A|B|Aprime|C|D> | all | teardown
# Every command and its output is logged to $R/logs/cluster-run.log.
set -uo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
H=$R/hadoop
CONF=$R/conf
OUT=$R/logs/cluster
JARS=$R/jars
U=$(whoami)
MNT=/mnt/hdfs-nfs-$U
NFSJAR=$H/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$H HADOOP_CONF_DIR=$CONF
export PATH=$JAVA_HOME/bin:$H/bin:$PATH
mkdir -p "$OUT" "$R/logs"
exec > >(tee -a "$R/logs/cluster-run.log") 2>&1
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
nfspid() { jps | awk '$2=="Nfs3"{print $1}'; }
barr() {  # $1 pid, $2 histogram file -> prints live [B bytes; keeps the top of the histogram
  $JAVA_HOME/bin/jcmd "$1" GC.class_histogram > "$2.full" 2>&1
  head -25 "$2.full" > "$2"; grep -E 'nfs3\.WriteCtx|OffsetRange' "$2.full" >> "$2"; rm -f "$2.full"
  awk '$4=="[B"{print $3}' "$2"; }
jarconst() { $JAVA_HOME/bin/javap -c -p -constants -classpath "$1" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx \
  | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1; }
registered() { rpcinfo -p localhost 2>/dev/null | grep -qE '100003 +3 +tcp +2049'; }
NFSLOG() { ls "$R"/logs/hadoop/hadoop-$U-nfs3-*.log 2>/dev/null | head -1; }

prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }

do_jars() {
  echo "=== jars $(date '+%F %T %Z')"
  mkdir -p "$JARS"
  cd "$SRC" || fail "no src"
  [ -z "$(git status --short -- "$MOD/src/main")" ] || fail "main source not clean"
  run cp "$DIST/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-stock.jar"
  for v in 64m inf; do
    if [ $v = 64m ]; then val='64L * 1024 * 1024'; else val='Long.MAX_VALUE'; fi
    run sed -i "73s/private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;/private static long DUMP_WRITE_WATER_MARK = $val;/" "$OFC"
    run sed -n 73p "$OFC"
    run git diff --stat
    run mvn -B -o -q package -pl "$MOD" -Dmaven.test.skip=true -Dmaven.javadoc.skip=true \
        > "$OUT/mvn-jar-$v.log" 2>&1 || fail "jar build $v failed"
    run cp "$SRC/$MOD/target/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-$v.jar"
    run git checkout -- "$OFC"
  done
  run git status --short
  # leave the copy's target/ with the stock class (never installed into ~/.m2)
  run mvn -B -o -q package -pl "$MOD" -Dmaven.test.skip=true -Dmaven.javadoc.skip=true \
      > "$OUT/mvn-jar-restock.log" 2>&1 || echo "restock build failed (not used)"
  for j in stock 64m inf; do
    echo "--- javap $j: $(jarconst "$JARS/nfs-$j.jar" | tee "$OUT/javap-$j.txt")"
  done
  run ls -l "$JARS"
}

do_setup() {
  echo "=== setup $(date '+%F %T %Z') on $(hostname)"
  [ -d "$H" ] || run cp -a "$DIST" "$H"
  rm -rf "$CONF"; run cp -r "$H/etc/hadoop" "$CONF"
  mkdir -p "$R/tmp" "$R/nn" "$R/dn" "$R/dump" "$R/pids" "$R/logs/hadoop"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$R/tmp"
    prop hadoop.proxyuser.$U.hosts '*'
    prop hadoop.proxyuser.$U.groups '*'
    echo '</configuration>'; } > "$CONF/core-site.xml"
  write_hdfs_site true
  cat >> "$CONF/hadoop-env.sh" <<EOF
export HADOOP_LOG_DIR=$R/logs/hadoop
export HADOOP_PID_DIR=$R/pids
export JAVA_HOME=$JAVA_HOME
EOF
  echo 'log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG' >> "$CONF/log4j.properties"
  run cat "$CONF/core-site.xml" "$CONF/hdfs-site.xml"
  run tail -4 "$CONF/hadoop-env.sh"; run tail -1 "$CONF/log4j.properties"
  run hdfs namenode -format -nonInteractive > "$OUT/nn-format.log" 2>&1 || fail "format"
  run hdfs --daemon start namenode
  run hdfs --daemon start datanode
  run hdfs dfsadmin -safemode wait
  run hdfs dfs -mkdir -p /nfstest
  run hdfs dfs -chmod 777 /nfstest
  run hdfs dfsadmin -report | head -12
  run jps
  sudo mkdir -p "$MNT"
}

write_hdfs_site() {
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.replication 1
    prop dfs.namenode.name.dir "$R/nn"
    prop dfs.datanode.data.dir "$R/dn"
    prop nfs.dump.dir "$R/dump"
    prop nfs.exports.allowed.hosts '* rw'
    prop nfs.stream.timeout 60000
    prop nfs.wtmax 1048576
    prop nfs.file.dump "$1"
    echo '</configuration>'; } > "$CONF/hdfs-site.xml"
}

start_gateway() {  # $1 = Xmx
  export HDFS_NFS3_OPTS="-Xmx$1 -Xms$1"
  run hdfs --daemon start nfs3
  for i in $(seq 1 30); do
    sleep 2
    if registered; then break; fi
    [ -n "$(nfspid)" ] || break
  done
  if ! registered; then
    echo "gateway not registered with the running portmapper; log tail:"
    tail -20 "$(NFSLOG)"
    if [ ! -e "$R/pids/rpcbind-stopped" ]; then
      echo "falling back to the Hadoop portmap (B3e step 2): stop system rpcbind"
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
  echo "nfs3 pid $(nfspid); cmdline Xmx: $(tr '\0' ' ' < /proc/$(nfspid)/cmdline | grep -o -- '-Xmx[^ ]*' | tr '\n' ' ')"
}

stop_gateway() {
  mountpoint -q "$MNT" && { run sudo umount "$MNT" || run sudo umount -f -l "$MNT"; }
  if [ -n "$(nfspid)" ]; then run hdfs --daemon stop nfs3; fi
  sleep 2
  p=$(nfspid); [ -n "$p" ] && { echo "nfs3 still alive, kill -9 $p"; kill -9 $p; }
  true
}

install_jar() {  # $1 = stock|64m|inf
  run cp "$JARS/nfs-$1.jar" "$NFSJAR.new"
  run mv -f "$NFSJAR.new" "$NFSJAR"      # rename: running NN/DN keep the old inode
  jarconst "$NFSJAR"
}

do_arm() {
  local arm=$1 jar xmx n hold dumpflag mopt limit
  mopt="vers=3,proto=tcp,nolock,noacl,soft,timeo=600,retrans=2,wsize=1048576"
  case $arm in
    A)      jar=stock; xmx=512m; n=1500; hold=40; dumpflag=true;  limit=900 ;;
    B)      jar=64m;   xmx=512m; n=1500; hold=40; dumpflag=true;  limit=900 ;;
    Aprime) jar=stock; xmx=384m; n=8192; hold=40; dumpflag=true;  limit=1500 ;;
    C)      jar=inf;   xmx=384m; n=8192; hold=40; dumpflag=true;  limit=600 ;;
    D)      jar=stock; xmx=512m; n=64;   hold=10; dumpflag=false; limit=120
            mopt="vers=3,proto=tcp,nolock,noacl,soft,timeo=100,retrans=2,wsize=1048576" ;;
    *) fail "unknown arm $arm" ;;
  esac
  local A=$OUT/arm-$arm; mkdir -p "$A"
  cd "$R" || fail "cd"
  echo "=== arm $arm jar=$jar xmx=$xmx N=$n hold=$hold nfs.file.dump=$dumpflag $(date '+%F %T %Z')"
  stop_gateway
  write_hdfs_site $dumpflag
  install_jar $jar | tee "$A/jar-const.txt"
  local l0=0; [ -n "$(NFSLOG)" ] && l0=$(wc -l < "$(NFSLOG)")
  start_gateway $xmx
  local PID; PID=$(nfspid)
  run sudo mount -t nfs -o "$mopt" localhost:/ "$MNT" || fail "mount"
  run ls -la "$MNT/nfstest"
  run readlink /proc/$PID/cwd
  sleep 3
  local H0; H0=$(barr $PID "$A/histo-H0.txt"); echo "H0 [B live bytes: $H0" | tee "$A/H0.txt"
  $JAVA_HOME/bin/jcmd $PID GC.heap_info > "$A/heapinfo-H0.txt" 2>&1
  echo "dump dir at start: $(du -sb "$R/dump" | cut -f1)" | tee "$A/dump-start.txt"
  $JAVA_HOME/bin/jstat -gc $PID 1000 > "$A/jstat.txt" 2>&1 &
  local JST=$!
  local F=$MNT/nfstest/$arm-$(date +%s)
  echo "file $F"
  timeout -s KILL $limit python3 "$R/harness/ooo_write.py" "$F" 65536 $n $hold > "$A/client.txt" 2>&1 &
  local PY=$!
  local held=no
  while kill -0 $PY 2>/dev/null; do
    if [ $held = no ] && grep -q '^HOLD' "$A/client.txt"; then
      held=yes
      echo "HOLD seen $(date '+%F %T.%N %Z')"; cat "$A/client.txt" | tail -2
      tail -n +$((l0 + 1)) "$(NFSLOG)" > "$A/nfs3-at-hold.log"
      local H1; H1=$(barr $PID "$A/histo-H1.txt"); echo "H1 [B live bytes: $H1  delta: $((H1 - H0))" | tee "$A/H1.txt"
      $JAVA_HOME/bin/jcmd $PID GC.heap_info > "$A/heapinfo-H1.txt" 2>&1
      { echo "dump dir at hold: $(du -sb "$R/dump" | cut -f1)"; ls -l "$R/dump"; } | tee "$A/dump-hold.txt"
      echo "measured at $(date '+%F %T.%N %Z')"
    fi
    sleep 1
  done
  wait $PY; local rc=$?
  echo "client exit $rc"; run cat "$A/client.txt"
  if [ $held = no ]; then
    echo "no HOLD reached; state now:"
    if [ -n "$(nfspid)" ]; then local H1; H1=$(barr $(nfspid) "$A/histo-H1-end.txt"); echo "H1(end) [B live bytes: $H1" | tee "$A/H1-end.txt"; else echo "gateway process gone" | tee "$A/H1-end.txt"; fi
  fi
  { echo "dump dir after client: $(du -sb "$R/dump" | cut -f1)"; ls -l "$R/dump"; } | tee "$A/dump-after.txt"
  hdfs dfs -ls /nfstest/ | tee "$A/hdfs-ls.txt"
  hdfs dfs -stat '%b %n' "/nfstest/$(basename "$F")" 2>&1 | tee "$A/hdfs-stat.txt"
  if [ $rc = 0 ]; then
    echo "waiting nfs.stream.timeout + 10 s"; sleep 70
    { echo "dump dir after timeout: $(du -sb "$R/dump" | cut -f1)"; ls -l "$R/dump"; } | tee "$A/dump-after-timeout.txt"
    hdfs dfs -stat '%b %n' "/nfstest/$(basename "$F")" 2>&1 | tee -a "$A/hdfs-stat.txt"
  fi
  kill $JST 2>/dev/null
  echo "gateway alive: $(nfspid)"
  tail -n +$((l0 + 1)) "$(NFSLOG)" > "$A/nfs3.log"
  cp "$R"/logs/hadoop/hadoop-$U-nfs3-*.out "$A/" 2>/dev/null
  grep -c OutOfMemoryError "$A/nfs3.log" "$A"/*.out 2>/dev/null | tee "$A/oom-count.txt"
  stop_gateway
  hdfs dfs -rm -skipTrash "/nfstest/$(basename "$F")" > /dev/null 2>&1
  echo "=== arm $arm end $(date '+%F %T %Z')"
}

do_teardown() {
  echo "=== teardown $(date '+%F %T %Z')"
  stop_gateway
  if [ -n "$(sudo $JAVA_HOME/bin/jps | awk '$2=="Portmap"')" ]; then
    run sudo -E env PATH="$PATH" HADOOP_CONF_DIR="$CONF" HADOOP_HOME="$H" JAVA_HOME="$JAVA_HOME" \
        HDFS_PORTMAP_USER=root HADOOP_PID_DIR="$R/pids" HADOOP_LOG_DIR="$R/logs/hadoop" "$H/bin/hdfs" --daemon stop portmap
  fi
  if [ -e "$R/pids/rpcbind-stopped" ]; then
    run sudo systemctl start rpcbind.socket rpcbind && rm -f "$R/pids/rpcbind-stopped"
  fi
  run hdfs --daemon stop datanode
  run hdfs --daemon stop namenode
  sleep 3
  run jps
  run sudo $JAVA_HOME/bin/jps
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[N]fs3|[P]ortmap|[o]oo_write|[j]stat -gc' || echo "no daemon left"
  mountpoint -q "$MNT" && echo "MOUNT STILL PRESENT" || echo "mount gone"
  sudo rmdir "$MNT" 2>/dev/null
  run systemctl is-active rpcbind
  run rpcinfo -p localhost
}

case ${1:-} in
  jars) do_jars ;;
  setup) do_setup ;;
  arm) do_arm "$2" ;;
  teardown) do_teardown ;;
  all) trap 'echo "EXIT trap: teardown"; do_teardown' EXIT
       do_jars; do_setup; for a in A B Aprime C D; do do_arm $a; done ;;
  *) fail "usage" ;;
esac
