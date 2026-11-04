#!/usr/bin/env bash
# Unit tier for local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous (stage 4, set A batch 8, tag ls, port slot 6; no ports used).
# Usage: bash unit-run.sh <run-label>     (needs sudo for tmpfs mounts)
# Tree ~/s4-b8-ls-u (copy-source.sh + ant build-test). Output ~/s4-b8-ls-logs/unit-<label>/{summary.txt,...}. Exit 1 on any failed EXPECTED.
set -u
RUN=${1:?run label}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$HOME/s4-b8-ls-u; W=$HOME/s4-b8-ls-unitwork; M=$HOME/s4-b8-ls-mnt; L=$HOME/s4-b8-ls-logs/unit-$RUN
mkdir -p "$L" "$W" "$M"; SUM=$L/summary.txt; : > "$SUM"
say(){ echo "$@" | tee -a "$SUM"; }
FAIL=0
cleanup(){ for d in "$M"/*; do mountpoint -q "$d" 2>/dev/null && sudo umount "$d"; done; rm -rf "$W/storage"; say "cleanup: mounts left=$(mount | grep -c "$M")"; }
trap cleanup EXIT
ulimit -n 100000
cd "$T" || exit 1
cp "$HERE/SysDirFreeSpaceWarnTest.java" test/unit/org/apache/cassandra/config/
cp "$HERE/CommitLogTotalSpaceCapTest.java" test/unit/org/apache/cassandra/db/commitlog/
CP="build/classes/main:build/test/classes:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar lib/*.jar 2>/dev/null | tr '\n' ':')"
javac -nowarn -d build/test/classes -cp "$CP" test/unit/org/apache/cassandra/config/SysDirFreeSpaceWarnTest.java test/unit/org/apache/cassandra/db/commitlog/CommitLogTotalSpaceCapTest.java > "$L/javac.out" 2>&1 || { cat "$L/javac.out"; exit 2; }
OPTS=$(grep -v '^#' conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')

mnt(){ mkdir -p "$M/$1"; sudo mount -t tmpfs -o size=$2 tmpfs "$M/$1" && mkdir -p "$M/$1/sys" && sudo chown "$(id -u)" "$M/$1" "$M/$1/sys"
  say "mount $1 size=$2 -> avail $(df -B1 --output=avail "$M/$1" | tail -1) bytes"; }
umnt(){ sudo umount "$M/$1"; }
mkyaml(){ # label sysdir(or empty)
  rm -rf "$W/storage"; mkdir -p "$W/storage"/{commitlog,cdc_raw,hints,saved_caches,data}
  python3 - "$T/test/conf/cassandra.yaml" "$W/$1.yaml" "$W/storage" "$2" <<'PY'
import sys,re
src,dst,st,sysdir=sys.argv[1:]
s=open(src).read()
for k in ("commitlog_directory","cdc_raw_directory","hints_directory","saved_caches_directory"):
    s=re.sub(r"^%s:.*$"%k,"%s: %s/%s"%(k,st,k.replace("_directory","")),s,flags=re.M)
s=re.sub(r"^data_file_directories:\n    - .*\n","data_file_directories:\n    - %s/data\n"%st,s,flags=re.M)
if sysdir: s+="\nlocal_system_data_file_directory: %s\n"%sysdir
open(dst,"w").write(s)
PY
}
runcase(){ # label sysdir
  local label=$1 sysdir=$2
  mkyaml "$label" "$sysdir"
  say "--- case $label (local_system_data_file_directory=${sysdir:-unset})"
  java -Xmx512m $OPTS -Dcassandra.config=file://$W/$label.yaml -Dcassandra.storagedir=$W/storage -Dstage4.label=$label -Dstage4.sysdir="$sysdir" -Dstage4.dumpconfig=$L/$label.config.txt -Dcassandra.skip_sync=true -Dlogback.configurationFile=file://$T/test/conf/logback-test.xml -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.config.SysDirFreeSpaceWarnTest > "$L/$label.out" 2>&1
  echo "exit=$?" >> "$L/$label.out"
  sed -n 's/^.* - \(STAGE4 .*\)$/\1/p; s/^\(STAGE4 .*\)$/\1/p' "$L/$label.out" | awk '!s[$0]++' > "$L/$label.stage4"
  grep -E '^OK|^FAIL|Tests run|^exit=' "$L/$label.out" >> "$L/$label.stage4"
  sed 's/^/    /' "$L/$label.stage4" >> "$SUM"; sed 's/^/    /' "$L/$label.stage4"
}
has(){ grep -qE "$2" "$L/$1.stage4"; }
expect(){ # label desc regex
  if has "$1" "$3"; then say "EXPECTED OK: [$1] $2"; else say "EXPECTED FAIL: [$1] $2 (pattern: $3)"; FAIL=1; fi; }
stopif(){ [ $FAIL = 0 ] || { say "STOP: first-trigger check failed; no later case run"; exit 1; }; }
GIB=1073741824

# case 1 (first trigger): 0.5 GiB must warn once
mnt v05 536870912
runcase s05 "$M/v05/sys"
expect s05 "unallocated=536870912" "unallocated_bytes=536870912 "
expect s05 "one sys WARN 'Only 512.000MiB free in the system data volume'" "sys_warn_count=1 "
expect s05 "WARN text" "sys_warn_text=Only 512.000MiB free in the system data volume"
expect s05 "init returned" "init_returned=true error=none"
expect s05 "300 MiB request admitted below the 1 GiB line" "probe request=314572800 result=returned_directory"
expect s05 "twice-available request refused" "probe request=[0-9]+ result=threw_FSDiskFullWriteError"
stopif
# control inside the same volume: sysdir unset (yaml has no key), volume still mounted
runcase unset ""
expect unset "no sys WARN with the directory unset" "sys_warn_count=0 "
expect unset "init returned" "init_returned=true error=none"
umnt v05
# exactly 1 GiB
mnt v10 $GIB
runcase s10 "$M/v10/sys"
expect s10 "unallocated=1073741824" "unallocated_bytes=1073741824 one_gib=1073741824 lt_one_gib=false"
expect s10 "no sys WARN at exactly 1 GiB (strict <)" "sys_warn_count=0 "
expect s10 "init returned" "init_returned=true error=none"
umnt v10
# one page below 1 GiB (extra boundary case, not a B2 row)
mnt v10m 1073737728
runcase s10m "$M/v10m/sys"
expect s10m "unallocated=1073737728 (1 GiB - 4096)" "unallocated_bytes=1073737728 .*lt_one_gib=true"
expect s10m "one sys WARN one page below the line" "sys_warn_count=1 "
umnt v10m
# 1.5 GiB
mnt v15 1610612736
runcase s15 "$M/v15/sys"
expect s15 "unallocated=1610612736" "unallocated_bytes=1610612736 "
expect s15 "no sys WARN" "sys_warn_count=0 "
expect s15 "init returned" "init_returned=true error=none"
expect s15 "300 MiB request admitted" "probe request=314572800 result=returned_directory"
expect s15 "twice-available request refused" "probe request=[0-9]+ result=threw_FSDiskFullWriteError"
umnt v15
# Config dump identical (all fields but the two directory lists) across values
if cmp -s "$L/s05.config.txt" "$L/s10.config.txt" && cmp -s "$L/s05.config.txt" "$L/s15.config.txt" && cmp -s "$L/s05.config.txt" "$L/unset.config.txt"; then say "EXPECTED OK: Config dump (all fields but the directory lists) identical for 0.5 GiB, 1 GiB, 1.5 GiB and unset"; else say "EXPECTED FAIL: Config dump differs"; diff "$L/s05.config.txt" "$L/s15.config.txt" | head -5 | tee -a "$SUM"; FAIL=1; fi
n_sys=$(grep -h 'free in the system data volume' "$L"/s05.out "$L"/s10.out "$L"/s15.out "$L"/unset.out | grep -c WARN); say "raw lines with the sys WARN across the four main cases: $n_sys (expect 1)"

# positive control: commit-log cap (own JVMs, ant testsome), capped 32 MiB vs uncapped
TEST=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceCapTest
for arm in 32 100000; do
  D=$L/cl$arm; mkdir -p "$D"
  rm -rf build/test/cassandra build/test/logs; rm -f build/test/output/TEST-$TEST.xml
  say "+ CLCAP_MIB=$arm CLCAP_SLEEP_MS=10 CLCAP_N=300 ant testsome -Dtest.name=$TEST -Dno-build-test=true"
  CLCAP_MIB=$arm CLCAP_SLEEP_MS=10 CLCAP_N=300 CLCAP_OUT=$D/cap.csv ant testsome -Dtest.name=$TEST -Dno-build-test=true </dev/null > "$D/ant.log" 2>&1
  say "ant rc=$? $(grep -E 'Tests run:|BUILD' $D/ant.log | tr '\n' ' ')"
  cp build/test/output/TEST-$TEST.xml "$D/" 2>/dev/null
  mkdir -p "$D/testlogs"; cp -r build/test/logs/. "$D/testlogs/" 2>/dev/null
  tl(){ find "$D/testlogs" -type f -print0 | sort -z | xargs -0 zcat -f; }
  echo "COMMITLOG_DIRTY $(tl | grep -c 'Enqueuing flush of CLCapKS.t, Reason: COMMITLOG_DIRTY')" > "$D/reasons.txt"
  cat "$D/cap.csv.summary" "$D/reasons.txt" 2>/dev/null | tee -a "$SUM"
done
python3 - "$L" <<'PY' | tee -a "$SUM"
import sys,re
L=sys.argv[1]; r={}
for a in ("32","100000"):
    t=open("%s/cl%s/cap.csv.summary"%(L,a)).read()+open("%s/cl%s/reasons.txt"%(L,a)).read()
    m=re.search(r"peakOnDisk=(\d+)",t); d=re.search(r"COMMITLOG_DIRTY (\d+)",t)
    r[a]=(int(m.group(1)),int(d.group(1)))
mib=1<<20
ok=r["32"][0]<=52*mib and r["100000"][0]>300*mib and r["32"][1]>0 and r["100000"][1]==0
print("control peaks MiB: capped %.1f (dirty flushes %d), uncapped %.1f (dirty flushes %d)"%(r["32"][0]/mib,r["32"][1],r["100000"][0]/mib,r["100000"][1]))
print("EXPECTED %s: capped peak <= 52 MiB, uncapped > 300 MiB, COMMITLOG_DIRTY >0 capped and 0 uncapped"%("OK" if ok else "FAIL"))
sys.exit(0 if ok else 1)
PY
[ ${PIPESTATUS[0]} = 0 ] || FAIL=1
say "unit-run $RUN done FAIL=$FAIL"; exit $FAIL
