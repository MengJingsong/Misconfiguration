#!/usr/bin/env bash
# Stage-4 cluster tier (B3, amended D1-3/D1-4/D1-6) for
# dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous (Jingsong queue order 26). Runs on pc91.
# Usage: cluster-run.sh all|stop|teardown
#   all:      setup + B3e steps 1-9 for C0..C4 (C0 first: it makes the plan template)
#   stop:     stop daemons and the sampler (idempotent)
#   teardown: stop, then delete bulk data (in.bin, dn, nn, tmp, hadoop copy); keep logs, plans, readings
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
MODE=${1:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
BLK=16777216
META=131079
C=$((BLK + META))          # 16908295
GIB=1073741824
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_PID_DIR=$RUN/pids
export HADOOP_LOG_DIR=$RUN/logs HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
SRCV=$RUN/dn/vol-src
DSTV=$RUN/dn/vol-dst
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
dnlog() { ls "$HADOOP_LOG_DIR"/hadoop-*-datanode-*.log 2>/dev/null | head -1; }
# vol <src|dst> <field>: from DataNode JMX VolumeInfo (keyed by the volume's base dir)
volall() { curl -s 'http://localhost:19864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | python3 -I -c '
import json,sys
b=json.load(sys.stdin)["beans"][0]; v=json.loads(b["VolumeInfo"])
out=[]
for k,d in sorted(v.items()):
    n="src" if k.rstrip("/").endswith("vol-src") else ("dst" if k.rstrip("/").endswith("vol-dst") else k)
    out.append("%s:used=%d,free=%d,reserved=%d,rfr=%d,blocks=%d" % (n,d["usedSpace"],d["freeSpace"],d["reservedSpace"],d["reservedSpaceForReplicas"],d["numBlocks"]))
print(" ".join(out))' 2>/dev/null; }
vol() { volall | tr ' ' '\n' | awk -F'[:,=]' -v n="$1" -v f="$2" '$1==n{for(i=2;i<NF;i+=2) if($i==f) print $(i+1)}'; }
statf() { stat -f -c '%S %b %f %a' "$DSTV"; }
stop_sampler() { if [ -f "$RUN/sampler.pid" ]; then kill "$(cat "$RUN/sampler.pid")" 2>/dev/null; rm -f "$RUN/sampler.pid"; fi; }
stopall() {
  stop_sampler
  [ -x "$HADOOP_HOME/bin/hdfs" ] && { hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; }
  sleep 3
  echo "+ ps check:"
  if ps -u "$(id -un)" -o pid=,args= | awk -v r="$RUN" '/proc_namenode|proc_datanode/ && index($0, r) && !/awk/' | grep -q .; then
    ps -u "$(id -un)" -o pid=,args= | awk -v r="$RUN" '/proc_namenode|proc_datanode/ && index($0, r) && !/awk/' | cut -c1-140; echo "  WARN: daemons left"
  else echo "  no NameNode/DataNode of this run"; fi; }
die() { echo "STOP: $*"; stopall; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
write_core() {
  { echo '<?xml version="1.0"?><configuration>'
    prop fs.defaultFS hdfs://localhost:19000
    prop hadoop.tmp.dir "$RUN/tmp"
    prop fs.du.interval 3600000
    echo '</configuration>'; } > "$RUN/conf/core-site.xml"; }
# write_hdfs <data.dir list> [R for vol-dst]
write_hdfs() {
  { echo '<?xml version="1.0"?><configuration>'
    prop dfs.namenode.name.dir "$RUN/nn"
    prop dfs.replication 1
    prop dfs.blocksize $BLK
    prop dfs.disk.balancer.enabled true
    prop dfs.namenode.http-address 0.0.0.0:19870
    prop dfs.namenode.secondary.http-address 0.0.0.0:19868
    prop dfs.datanode.address 0.0.0.0:19866
    prop dfs.datanode.http.address 0.0.0.0:19864
    prop dfs.datanode.ipc.address 0.0.0.0:19867
    prop dfs.datanode.data.dir "$1"
    [ -n "${2:-}" ] && prop "dfs.datanode.du.reserved.$DSTV" "$2"
    echo '</configuration>'; } > "$RUN/conf/hdfs-site.xml"
  grep -E 'data.dir|du.reserved' "$RUN/conf/hdfs-site.xml"; }
wait_live() {  # wait until the NN reports 1 live DN and the DN JMX lists $1 volumes
  for i in $(seq 1 60); do
    if hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && [ "$(volall | wc -w)" -eq "$1" ]; then return 0; fi
    sleep 2; done; return 1; }
wait_blocks() {  # wait_blocks <src> <dst> (numBlocks per volume; dst may be '-' when not attached)
  for i in $(seq 1 90); do
    local s=$(vol src blocks) d=$(vol dst blocks)
    if [ "$s" = "$1" ] && { [ "$2" = "-" ] || [ "$d" = "$2" ]; }; then echo "  blocks src=$s dst=${d:--}"; return 0; fi
    sleep 2; done; echo "  blocks src=$(vol src blocks) dst=$(vol dst blocks) (timeout)"; return 1; }
restart_dn() { run hdfs --daemon stop datanode; sleep 2; run hdfs --daemon start datanode || die "dn start"; }

case "$MODE" in
stop) stopall; exit 0 ;;
teardown) stopall; run rm -rf "$RUN/in.bin" "$RUN/dn" "$RUN/nn" "$RUN/tmp" "$RUN/hadoop"; run du -sh "$RUNDIR"; exit 0 ;;
all) ;;
*) echo "bad mode"; exit 2 ;;
esac
trap 'stopall' EXIT

echo "=== cluster-run.sh all start $(date '+%F %T %Z') host=$(hostname)"
run java -version
for p in 19000 19864 19866 19867 19868 19870; do ss -ltn | awk -v p=":$p" '$4 ~ p"$"' | grep -q . && die "port $p busy"; done
echo "  ports 19000 19864 19866 19867 19868 19870 free"
[ -e "$RUN" ] && die "$RUN exists (fresh start expected)"
mkdir -p "$RUN" "$SRCV" "$DSTV" "$RUN/pids" "$RUN/logs"
run cp -a "$DIST" "$RUN/hadoop" || die "copy dist"
run cp -r "$RUN/hadoop/etc/hadoop" "$RUN/conf" || die "copy conf"
write_core
run hdfs version | head -1

# ---- B3e step 1: format, start, both volumes with no reserve
write_hdfs "$SRCV,$DSTV"
run hdfs namenode -format -force -nonInteractive > "$LOGS/format.log" 2>&1 || die format
run hdfs --daemon start namenode || die "nn start"
run hdfs --daemon start datanode || die "dn start"
run hdfs dfsadmin -safemode wait
wait_live 2 || die "datanode not live with 2 volumes"
HDN=$(hdfs dfsadmin -report 2>/dev/null | awk -F': ' '/^Hostname:/{print $2; exit}')
SRCID=$(awk -F= '/^storageID=/{print $2}' "$SRCV/current/VERSION")
DSTID=$(awk -F= '/^storageID=/{print $2}' "$DSTV/current/VERSION")
echo "  H_DN=$HDN srcId=$SRCID dstId=$DSTID; JMX: $(volall)"
[ -n "$HDN" ] && [ -n "$SRCID" ] && [ -n "$DSTID" ] || die "no hostname/storage IDs"
run bash -c "head -c 2147483648 /dev/urandom > '$RUN/in.bin'" || die "in.bin"
run ls -l "$RUN/in.bin"

printf 'run,R,A0target,A0,usedDst0,blocks0src,blocks0dst,duDst0,statf0,B,tol,blocksCopied,bytesCopied,usedDst1,freeDst1,dUsed,duDst1,dDu,statf1,H1,intrusion,minFreeSampled,nPred,l1148,l1110,l1121,l1102,result\n' > "$LOGS/readings.csv"

onerun() {  # onerun <label> <A0 target or -1> <B> <tol>
  local L=$1 T=$2 BB=$3 TOL=$4
  echo "===================== $L: A0target=$T B=$BB tol=$TOL  [$(date '+%T')]"
  # step 2: load
  if hdfs dfs -test -e /data/f 2>/dev/null; then
    run hdfs dfs -rm -skipTrash /data/f
    wait_blocks 0 0 || die "$L: blocks not deleted"
  fi
  local UDST=$(vol dst used); echo "  U_dst before stop = $UDST; JMX: $(volall)"
  run hdfs --daemon stop datanode; sleep 2
  write_hdfs "$SRCV"
  run hdfs --daemon start datanode || die "dn start (load)"
  wait_live 1 || die "$L: DN not live (load)"
  run hdfs dfs -mkdir -p /data
  run hdfs dfs -put "$RUN/in.bin" /data/f || die "$L: put"
  local NB=$(hdfs fsck /data/f -files -blocks 2>/dev/null | awk '/Total blocks \(validated\)/{print $4}')
  echo "  fsck total blocks = $NB"; [ "$NB" = 128 ] || die "$L: fsck blocks $NB != 128"
  # step 3: balance phase with the reserve
  run hdfs --daemon stop datanode; sleep 2
  local R=""
  if [ "$T" -ge 0 ]; then
    read S Bt F A < <(statf)
    R=$(( S*(Bt - F + A) - UDST - T ))
    echo "  statf=$S $Bt $F $A U_dst=$UDST -> R=$R"
  fi
  write_hdfs "$SRCV,$DSTV" "$R"
  run hdfs --daemon start datanode || die "dn start (balance)"
  wait_live 2 || die "$L: DN not live (balance)"
  # step 4: verify the knob
  local RD=$(vol dst reserved) RS=$(vol src reserved)
  echo "  KNOB $L: reserved dst=$RD (R=${R:-0}) src=$RS"
  [ "$RD" = "${R:-0}" ] && [ "$RS" = 0 ] || die "$L: knob not applied"
  # step 5: plan
  if [ "$L" = C0 ]; then
    run hdfs diskbalancer -plan "$HDN" -thresholdPercentage 0.01 -out /dbplan > "$LOGS/plan-C0.out" 2>&1
    cat "$LOGS/plan-C0.out" | grep -v '^\s*$' | tail -8
    run hdfs dfs -ls /dbplan
    run hdfs dfs -get "/dbplan/$HDN.plan.json" "$RUN/plan-template.json" || die "no plan template"
    run hdfs dfs -rm -r -skipTrash /dbplan          # D1-4
    cp "$RUN/plan-template.json" "$LOGS/"
  fi
  python3 -I - "$RUN/plan-template.json" "$RUN/plan-$L.json" "$DSTID" "$BB" "$TOL" <<'EOF' || die "$L: plan edit"
import json,sys,time
src,dst,dstid,bb,tol=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5])
p=json.load(open(src))
steps=[s for s in p["volumeSetPlans"] if s["destinationVolume"]["uuid"]==dstid]
assert len(steps)==1, "steps to dst: %d of %d" % (len(steps), len(p["volumeSetPlans"]))
s=steps[0]; s["bytesToMove"]=bb; s["tolerancePercent"]=tol; s["bandwidth"]=100
p["volumeSetPlans"]=[s]; p["timeStamp"]=int(time.time()*1000)
json.dump(p,open(dst,"w"))
print("  plan: node=%s port=%s src=%s dst=%s bytesToMove=%d tol=%d bw=%d" % (p["nodeName"],p["port"],s["sourceVolume"]["uuid"],s["destinationVolume"]["uuid"],s["bytesToMove"],s["tolerancePercent"],s["bandwidth"]))
EOF
  cp "$RUN/plan-$L.json" "$LOGS/"
  wait_blocks 128 0 || die "$L: block counts at A0 time are not 128/0 (D1-4)"
  # step 6: A0
  local A0=$(vol dst free) U0=$(vol dst used) DU0=$(du -sb "$DSTV/current" | cut -f1) SF0=$(statf)
  echo "  A0 $L: freeSpace(dst)=$A0 usedSpace(dst)=$U0 du(dst/current)=$DU0 statf=$SF0; JMX: $(volall)"
  # step 7: execute with the sampler
  ( while :; do echo "$(date +%s.%N) $(volall)"; sleep 1; done ) > "$LOGS/jmx-$L.log" 2>&1 &
  echo $! > "$RUN/sampler.pid"
  local DL=$(dnlog); local N0=$(wc -l < "$DL")
  run hdfs diskbalancer -D fs.defaultFS=file:/// -execute "$RUN/plan-$L.json" > "$LOGS/execute-$L.out" 2>&1
  local erc=$?; tail -3 "$LOGS/execute-$L.out"; [ $erc = 0 ] || die "$L: execute rejected (rc=$erc)"
  local Q=""
  for i in $(seq 1 150); do
    hdfs diskbalancer -query localhost:19867 -v > "$LOGS/query-$L.out" 2>&1
    grep -q 'PLAN_DONE' "$LOGS/query-$L.out" && break; sleep 2; done
  sleep 2; stop_sampler
  cat "$LOGS/query-$L.out" | grep -v '^\s*$' | tail -20
  # step 8: record
  sed -n "$((N0+1)),\$p" "$DL" > "$LOGS/dn-$L.log"
  grep -nE 'enough space|Copy from|No source blocks|No movable source blocks|Exceeded the max error|Exception while trying to copy' "$LOGS/dn-$L.log" | cut -c1-300 > "$LOGS/stop-lines-$L.txt"
  cat "$LOGS/stop-lines-$L.txt"
  local l1148=$(grep -c 'does not have enough space' "$LOGS/dn-$L.log") l1110=$(grep -c 'Copy from .* done' "$LOGS/dn-$L.log")
  local l1121=$(grep -c 'No source blocks' "$LOGS/dn-$L.log") l1102=$(grep -c 'Exceeded the max error' "$LOGS/dn-$L.log")
  local BC=$(python3 -I -c '
import sys,re
t=open(sys.argv[1]).read()
m=re.search(r"\{.*\}", t, re.S)
import json
try:
    j=json.loads(m.group(0)); w=j["currentState"][0]["workItem"]
    print(w["blocksCopied"], w["bytesCopied"], w.get("errorCount",0), j.get("result"))
except Exception as e:
    bc=re.search(r"\"blocksCopied\"\s*:\s*(\d+)",t); by=re.search(r"\"bytesCopied\"\s*:\s*(\d+)",t); r=re.search(r"PLAN_\w+",t)
    ec=re.search(r"\"errorCount\"\s*:\s*(\d+)",t)
    print(bc.group(1) if bc else "NA", by.group(1) if by else "NA", ec.group(1) if ec else "NA", r.group(0) if r else "NA")' "$LOGS/query-$L.out")
  set -- $BC; local BLKC=$1 BYC=$2 RES=$4
  local U1=$(vol dst used) F1=$(vol dst free) DU1=$(du -sb "$DSTV/current" | cut -f1) SF1=$(statf)
  read S Bt F A <<< "$SF1"
  local RR=${R:-0}
  local H1=$(( S*Bt - S*(F - A) - RR - U1 ))
  local INTR=$(( (S*Bt - S*(F - A) - RR) - DU1 )); [ $INTR -lt 0 ] && INTR=0
  local MINF=$(awk '{for(i=2;i<=NF;i++) if($i ~ /^dst:/){split($i,a,/[=,]/); print a[4]}}' "$LOGS/jmx-$L.log" | sort -n | head -1)
  local NP=$(python3 -I -c "import math; a=$A0; b=$BB; c=$C; print(59 if $T < 0 else min(59, max(0, math.ceil((a-b)/c))))")
  echo "  RESULT $L: blocksCopied=$BLKC bytesCopied=$BYC result=$RES nPred(A0)=$NP usedDst $U0 -> $U1 (d=$((U1-U0)), pred n*c=$((NP*C))) du $DU0 -> $DU1 (d=$((DU1-DU0))) freeDst1=$F1 H1=$H1 (B-c=$((BB-C)), B=$BB) intrusion=$INTR minFreeSampled=$MINF lines 1148=$l1148 1110=$l1110 1121=$l1121 1102=$l1102"
  echo "$L,$RR,$T,$A0,$U0,128,0,$DU0,$SF0,$BB,$TOL,$BLKC,$BYC,$U1,$F1,$((U1-U0)),$DU1,$((DU1-DU0)),$SF1,$H1,$INTR,$MINF,$NP,$l1148,$l1110,$l1121,$l1102,$RES" >> "$LOGS/readings.csv"
}

onerun C0 -1 $GIB 10
onerun C1 1420361872 $GIB 10
onerun C2 1758527772 $GIB 10
onerun C3 1056833529 $GIB 10
onerun C4 13000000 10000000 100

# ---- step 10 (partial): stop daemons; bulk data removed by 'teardown'
stopall
echo "=== cluster-run.sh all end $(date '+%F %T %Z')"
