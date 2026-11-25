#!/usr/bin/env bash
# Cluster tier (B3, amendments A2-A6) for DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous. Runs ON the node.
# Usage: cluster-run.sh jars | setup | run <C1|C2|C3|C4|C5> | teardown
# Every command and its output goes to $R/logs/cluster-run.log.
set -uo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
H=$R/hadoop; CONF=$R/conf; JARS=$R/jars; MNT=$R/mnt; DUMP=$R/nfs-dump; OBS=$R/obs; HLOG=$R/logs/hadoop
U=$(whoami)
NFSJAR=$H/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$H HADOOP_CONF_DIR=$CONF
export PATH=$JAVA_HOME/bin:$H/bin:$PATH
mkdir -p "$R/logs" "$OBS"
exec > >(tee -a "$R/logs/cluster-run.log") 2>&1
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
nfspid() { jps 2>/dev/null | awk '$2=="Nfs3" || $2=="NoRegNfs3"{print $1}'; }
registered() { rpcinfo -p localhost 2>/dev/null | grep -qE '100003 +3 +tcp +2049'; }
listening() { ss -ltn 2>/dev/null | grep -q ':2049 ' && ss -ltn 2>/dev/null | grep -q ':4242 '; }

do_jars() {
  echo "=== jars $(date '+%F %T %Z')"
  mkdir -p "$JARS"; cd "$SRC" || fail "no src"
  [ -z "$(git status --short -- "$MOD/src/main")" ] || fail "main source not clean"
  run cp "$DIST/share/hadoop/hdfs/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-m1.jar"
  run sed -i '73s/private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;/private static long DUMP_WRITE_WATER_MARK = 64L * 1024 * 1024;/' "$OFC"
  run sed -n 73p "$OFC"
  run git diff --stat -- "$MOD/src/main"
  run mvn -B -o -q package -pl "$MOD" -Dmaven.test.skip=true -Dmaven.javadoc.skip=true > "$R/logs/mvn-jar-m64.log" 2>&1 || { git checkout -- "$OFC"; fail "jar build"; }
  run cp "$SRC/$MOD/target/hadoop-hdfs-nfs-3.4.2.jar" "$JARS/nfs-m64.jar"
  run git checkout -- "$OFC"
  run git status --short -- "$MOD/src/main"
  for j in m1 m64; do
    echo "--- javap $j: $(javap -c -p -constants -classpath "$JARS/nfs-$j.jar" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1)"
  done
  # launcher class (A4)
  mkdir -p "$R/launcher"
  run javac -cp "$("$H/bin/hadoop" classpath 2>/dev/null || "$DIST/bin/hadoop" classpath)" -d "$R/launcher" "$R/harness/NoRegNfs3.java"
  run ls -l "$JARS" "$R/launcher"
}

do_setup() {
  echo "=== setup $(date '+%F %T %Z') on $(hostname)"
  run ss -ltnup | grep -E ':(111|2049|4242|9000|9870|9864|9866|9867|50079)\b'
  [ -d "$H" ] || run cp -a "$DIST" "$H"
  [ -e "$NFSJAR.orig" ] || run cp "$NFSJAR" "$NFSJAR.orig"
  rm -rf "$CONF"; run cp -r "$H/etc/hadoop" "$CONF"
  mkdir -p "$R/tmp" "$R/nn" "$R/dn" "$R/pids" "$HLOG" "$MNT" "$DUMP"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$R/tmp"
    prop hadoop.proxyuser.$U.hosts '*'
    prop hadoop.proxyuser.$U.groups '*'
    echo '</configuration>'; } > "$CONF/core-site.xml"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.replication 1
    prop dfs.namenode.name.dir "file://$R/nn"
    prop dfs.datanode.data.dir "file://$R/dn"
    prop nfs.dump.dir "$DUMP"
    prop nfs.file.dump true
    prop nfs.stream.timeout 180000
    prop nfs.exports.allowed.hosts '* rw'
    echo '</configuration>'; } > "$CONF/hdfs-site.xml"
  cat >> "$CONF/hadoop-env.sh" <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_LOG_DIR=$HLOG
export HADOOP_PID_DIR=$R/pids
export HDFS_NAMENODE_OPTS="-Xmx1g"
export HDFS_DATANODE_OPTS="-Xmx1g"
EOF
  echo 'log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx=DEBUG' >> "$CONF/log4j.properties"
  run cat "$CONF/core-site.xml" "$CONF/hdfs-site.xml"
  run tail -5 "$CONF/hadoop-env.sh"; run tail -1 "$CONF/log4j.properties"
  run hdfs namenode -format -nonInteractive > "$R/logs/nn-format.log" 2>&1 || fail "format"
  run hdfs --daemon start namenode
  run hdfs --daemon start datanode
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2; done
  run hdfs dfs -mkdir -p /nfstest
  run hdfs dfs -chmod 777 /nfstest
  run hdfs dfsadmin -report | head -12
  run jps
}

stop_gateway() {
  if mountpoint -q "$MNT"; then run sudo umount "$MNT" || run sudo umount -f -l "$MNT"; fi
  local p; p=$(nfspid)
  if [ -n "$p" ]; then
    if [ -e "$R/pids/launcher.pid" ]; then run kill "$(cat "$R/pids/launcher.pid")"; echo "gateway $(cat "$R/pids/launcher.pid") stopped $(date +%T)" >> /mydata/s4/DRIVER-o16.pid; rm -f "$R/pids/launcher.pid"
    else run hdfs --daemon stop nfs3; fi
    sleep 3; p=$(nfspid); [ -n "$p" ] && { echo "gateway still alive, kill -9 $p"; kill -9 $p; sleep 1; }
  fi
  true
}

# start_gateway <xmx> <logname>; sets GWLOG
start_gateway() {
  local X=$1 name=$2
  if [ ! -e "$R/pids/use-launcher" ]; then
    export HDFS_NFS3_OPTS="-Xms$X -Xmx$X"
    run hdfs --daemon start nfs3
    for i in $(seq 1 30); do sleep 2; registered && break; done
    if registered; then GWLOG=$(ls "$HLOG"/hadoop-$U-nfs3-*.log | head -1); return 0; fi
    echo "nfs3 not registered with the system rpcbind (A4); log tail:"; tail -5 "$HLOG"/hadoop-$U-nfs3-*.log
    [ -n "$(nfspid)" ] && run hdfs --daemon stop nfs3
    sleep 2; touch "$R/pids/use-launcher"
  fi
  GWLOG=$HLOG/nfs3-launcher-$name.log
  rm -f "$GWLOG"
  local CP; CP="$R/launcher:$(hadoop classpath)"
  echo "+ [$(date '+%F %T %Z')] java -Xms$X -Xmx$X ... NoRegNfs3 (log $GWLOG)"
  setsid nohup java -Xms$X -Xmx$X -Dproc_nfs3 -Dhadoop.log.dir="$HLOG" -Dhadoop.log.file="$(basename "$GWLOG")" \
     -Dhadoop.root.logger=INFO,RFA -Dhadoop.home.dir="$H" -cp "$CP" NoRegNfs3 > "$HLOG/launcher-$name.out" 2>&1 < /dev/null &
  echo $! > "$R/pids/launcher.pid"; echo "gateway $! $(date +%T)" >> /mydata/s4/DRIVER-o16.pid
  for i in $(seq 1 30); do sleep 2; listening && break; done
  listening || fail "launcher gateway not listening"
  run cat "$HLOG/launcher-$name.out"
}

histo() {  # $1 pid $2 file -> "[B bytes"
  jcmd "$1" GC.class_histogram > "$2" 2>&1
  awk '$4=="[B"{print $3}' "$2"
}

# run_case NAME FILES CHUNK CHUNKS XMX WSIZE JAR
run_case() {
  local N=$1 F=$2 C=$3 K=$4 X=$5 W=$6 J=$7
  local O=$OBS/$N; rm -rf "$O"; mkdir -p "$O"
  echo "=== run $N files=$F chunk=$C chunks=$K xmx=$X wsize=$W jar=$J $(date '+%F %T %Z')"
  stop_gateway
  run cp "$JARS/nfs-$J.jar" "$NFSJAR.new"; run mv -f "$NFSJAR.new" "$NFSJAR"
  echo "jar constant: $(javap -c -p -constants -classpath "$NFSJAR" org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx | grep -B1 'putstatic.*DUMP_WRITE_WATER_MARK' | head -1)" | tee "$O/jar-const.txt"
  local L0=0
  start_gateway "$X" "$N"
  [ -f "$GWLOG" ] && L0=$(wc -l < "$GWLOG")
  local PID; PID=$(nfspid); echo "gateway pid $PID log $GWLOG from line $((L0+1))"; [ -n "$PID" ] || fail "no gateway"
  run ps -o pid,args -p "$PID" | cut -c1-300
  run ls -la "$DUMP"
  local MOPT="vers=3,proto=tcp,nolock,noacl,sync,soft,timeo=600,retrans=2,wsize=$W"
  [ -e "$R/pids/use-launcher" ] && MOPT="$MOPT,port=2049,mountport=4242,mountproto=tcp"
  run sudo mount -t nfs -o "$MOPT" localhost:/ "$MNT" || fail "mount"
  run grep " $MNT " /proc/mounts
  local D=$MNT/nfstest/$(echo "$N" | tr C c)
  run mkdir "$D" || fail "mkdir on mount"
  sleep 2
  echo "$(date +%T) BASELINE byte[]=$(histo "$PID" "$O/histo-baseline.txt")" | tee -a "$O/checkpoints.txt"
  jstat -gc "$PID" 1000 > "$O/jstat.log" 2>&1 & local JS=$!
  ( while sleep 1; do date +%T; ls -l "$DUMP"; du -sb "$DUMP"; done ) > "$O/dump.log" 2>&1 & local DL=$!
  ( while sleep 5; do echo "$(date +%T) $(jcmd "$PID" GC.class_histogram 2>/dev/null | awk '$4=="[B"{print $3}')"; done ) > "$O/histo-5s.log" 2>&1 & local HS=$!
  echo "samplers jstat=$JS dump=$DL histo=$HS"
  python3 "$R/harness/ooo_write.py" --dir "$D" --files "$F" --chunk "$C" --chunks "$K" > "$O/driver.log" 2>&1 & local PY=$!
  echo "driver pid $PY"
  local seen=0 t0; t0=$(date +%s)
  while kill -0 $PY 2>/dev/null; do
    local n; n=$(grep -cE 'CHECKPOINT|PAUSE' "$O/driver.log")
    while [ "$seen" -lt "$n" ]; do
      seen=$((seen+1))
      local line; line=$(grep -E 'CHECKPOINT|PAUSE' "$O/driver.log" | sed -n "${seen}p")
      echo "$(date +%T) [$line] byte[]=$(histo "$PID" "$O/histo-cp$seen.txt") dump=$(du -sb "$DUMP" | cut -f1)" | tee -a "$O/checkpoints.txt"
    done
    if [ $(( $(date +%s) - t0 )) -gt 2400 ]; then echo "driver over 40 min: killing"; kill $PY; fi
    sleep 1
  done
  wait $PY; echo "driver exit $?"; run cat "$O/driver.log"
  echo "$(date +%T) AFTER-DONE byte[]=$(histo "$PID" "$O/histo-done.txt") dump=$(du -sb "$DUMP" | cut -f1)" | tee -a "$O/checkpoints.txt"
  run ls -l "$DUMP"
  echo "waiting 200 s (A3)"; sleep 200
  echo "$(date +%T) DONE+200s byte[]=$(histo "$PID" "$O/histo-done200.txt") dump=$(du -sb "$DUMP" | cut -f1)" | tee -a "$O/checkpoints.txt"
  run ls -l "$DUMP"
  kill $JS $DL $HS 2>/dev/null; wait $JS $DL $HS 2>/dev/null
  run hdfs dfs -ls -R /nfstest
  local first; first=/nfstest/$(basename "$D")/f000
  local want; want=$(python3 -c "import hashlib,sys;h=hashlib.md5();b=b'\xab'*$C
for i in range($K): h.update(b)
print(h.hexdigest())")
  local got; got=$(hdfs dfs -cat "$first" | md5sum | cut -d' ' -f1)
  echo "md5 $first want=$want got=$got match=$([ "$want" = "$got" ] && echo yes || echo no)" | tee "$O/md5.txt"
  tail -n +$((L0 + 1)) "$GWLOG" > "$O/nfs3.log"
  {
    echo "maxCounter $(grep -o 'new value: [0-9]*' "$O/nfs3.log" | awk '{print $3}' | sort -n | tail -1)"
    echo "hits1MiB $(grep -c 'new value: 1048576$' "$O/nfs3.log")"
    echo "hits64MiB $(grep -c 'new value: 67108864$' "$O/nfs3.log")"
    echo "updates $(grep -c 'Update nonSequentialWriteInMemory' "$O/nfs3.log")"
    echo "createDump $(grep -c 'Create dump file' "$O/nfs3.log")"
    echo "askDump $(grep -c 'Asking dumper to dump' "$O/nfs3.log")"
    echo "startDump $(grep -c 'Start dump. Before dump' "$O/nfs3.log")"
    echo "OOM $(grep -c OutOfMemoryError "$O/nfs3.log")"
    echo "dumpErr $(grep -cE 'Got failure when creating dump|Dump data failed|Dumper got Throwable' "$O/nfs3.log")"
    echo "streamCleanup $(grep -cE 'There are [0-9]+ pending writes|Fail pending write' "$O/nfs3.log")"
  } | tee "$O/counter-summary.txt"
  stop_gateway
  run hdfs dfs -rm -r -skipTrash "/nfstest/$(basename "$D")"
  gzip -f "$O/nfs3.log"
  echo "=== run $N end $(date '+%F %T %Z')"
}

do_teardown() {
  echo "=== teardown $(date '+%F %T %Z')"
  stop_gateway
  [ -e "$NFSJAR.orig" ] && run cp "$NFSJAR.orig" "$NFSJAR"
  run hdfs --daemon stop datanode
  run hdfs --daemon stop namenode
  sleep 3
  run jps
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[N]fs3|[N]oRegNfs3|[P]ortmap|[o]oo_write' || echo "no daemon left"
  mountpoint -q "$MNT" && echo "MOUNT STILL PRESENT" || echo "mount gone"
  run systemctl is-active rpcbind
  run rpcinfo -p localhost
}

case ${1:-} in
  jars) do_jars ;;
  setup) do_setup ;;
  run) case ${2:-} in
         C1) run_case C1 1 65536 12288 256m 65536 m1 ;;
         C2) run_case C2 32 65536 256 512m 65536 m1 ;;
         C3) run_case C3 1 65536 16 256m 65536 m1 ;;
         C4) run_case C4 1 1048576 768 256m 1048576 m1 ;;
         C5) run_case C5 1 65536 12288 512m 65536 m64 ;;
         *) fail "run what?" ;;
       esac ;;
  teardown) do_teardown ;;
  *) fail "usage" ;;
esac
