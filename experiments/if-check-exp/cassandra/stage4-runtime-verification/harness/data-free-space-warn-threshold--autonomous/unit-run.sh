#!/usr/bin/env bash
# Unit tier for data-free-space-warn-threshold--autonomous (stage 4, set A batch 8, tag fs).
# Usage: bash unit-run.sh <run-label>      e.g. run1 or shake1.  Needs sudo (tmpfs mounts).
# Tree: ~/s4-b8-fs-u (built with ant build-test); the test class is copied in and compiled with javac.
# Output: ~/s4-b8-fs-logs/unit-<run-label>/{summary.txt,<case>.out,...}. Exits 1 on any failed EXPECTED check.
set -u
RUN=${1:?run label}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$HOME/s4-b8-fs-u
W=$HOME/s4-b8-fs-unitwork          # local-disk work dir (storage, yamls)
M=$HOME/s4-b8-fs-mnt               # tmpfs mount points
L=$HOME/s4-b8-fs-logs/unit-$RUN
mkdir -p "$L" "$W" "$M"
SUM=$L/summary.txt; : > "$SUM"
say(){ echo "$@" | tee -a "$SUM"; }
FAIL=0
cleanup(){ for d in "$M"/*; do mountpoint -q "$d" 2>/dev/null && sudo umount "$d"; done; rm -rf "$W/storage"; }
trap cleanup EXIT
ulimit -n 100000
cd "$T" || exit 1
cp "$HERE/DataFreeSpaceWarnTest.java" test/unit/org/apache/cassandra/config/
CP="build/classes/main:build/test/classes:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar lib/*.jar 2>/dev/null | tr '\n' ':')"
javac -nowarn -d build/test/classes -cp "$CP" test/unit/org/apache/cassandra/config/DataFreeSpaceWarnTest.java > "$L/javac.out" 2>&1 || { cat "$L/javac.out"; exit 2; }
OPTS=$(grep -v '^#' conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')

mnt(){ # name size
  mkdir -p "$M/$1"; sudo mount -t tmpfs -o size=$2 tmpfs "$M/$1" && mkdir -p "$M/$1/data" && sudo chown "$(id -u)" "$M/$1" "$M/$1/data"
  say "mount $1 size=$2 -> $(df -B1 --output=avail "$M/$1" | tail -1) bytes avail"; }
umnt(){ sudo umount "$M/$1"; }

mkyaml(){ # label withdirs(yes/no) dirs...
  local label=$1 with=$2; shift 2
  rm -rf "$W/storage"; mkdir -p "$W/storage"/{commitlog,cdc_raw,hints,saved_caches,data}
  python3 - "$T/test/conf/cassandra.yaml" "$W/$label.yaml" "$W/storage" "$with" "$@" <<'PY'
import sys,re
src,dst,st,with_,*dirs=sys.argv[1:]
s=open(src).read()
for k in ("commitlog_directory","cdc_raw_directory","hints_directory","saved_caches_directory"):
    s=re.sub(r"^%s:.*$"%k,"%s: %s/%s"%(k,st,k.split('_directory')[0].replace('commitlog','commitlog')),s,flags=re.M)
s=re.sub(r"^data_file_directories:\n(    - .*\n)+","",s,flags=re.M)
if with_=="yes":
    s+="\ndata_file_directories:\n"+"".join("    - %s\n"%d for d in dirs)
open(dst,"w").write(s)
PY
}

runcase(){ # label control(true/false) with(yes/no) dirs...  -> prints/records output
  local label=$1 ctl=$2 with=$3; shift 3
  local dirs=$(IFS=,; echo "$*")
  mkyaml "$label" "$with" "$@"
  say "--- case $label (dirs=$dirs, yaml data_file_directories=$with)"
  java -Xmx512m $OPTS -Dcassandra.config=file://$W/$label.yaml -Dcassandra.storagedir=$W/storage -Dstage4.label=$label -Dstage4.dirs="$dirs" -Dstage4.control=$ctl -Dstage4.dumpconfig=$L/$label.config.txt -Dcassandra.skip_sync=true -Dlogback.configurationFile=file://$T/test/conf/logback-test.xml -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.config.DataFreeSpaceWarnTest > "$L/$label.out" 2>&1
  echo "exit=$?" >> "$L/$label.out"
  # the test's System.out goes through Cassandra's logging: pull the STAGE4 lines into <case>.stage4
  sed -n 's/^.* - \(STAGE4 .*\)$/\1/p; s/^\(STAGE4 .*\)$/\1/p' "$L/$label.out" | awk '!s[$0]++' > "$L/$label.stage4"
  grep -E '^OK|^FAIL|Tests run|^exit=' "$L/$label.out" >> "$L/$label.stage4"
  sed 's/^/    /' "$L/$label.stage4" | tee -a "$SUM" >/dev/null
}
getn(){ grep -E "^STAGE4 \[$1\] warn_count=" "$L/$1.stage4" | sed 's/.*warn_count=//'; }
expect(){ # label what condition(shell test string) 
  local label=$1 want=$2 got
  got=$(getn "$label")
  if [ "$got" = "$want" ]; then say "EXPECTED OK: [$label] warn_count=$want"; else say "EXPECTED FAIL: [$label] warn_count want=$want got=${got:-none}"; FAIL=1; fi; }
expect_ret(){ grep -q "^STAGE4 \[$1\] init_returned=true" "$L/$1.stage4" && say "EXPECTED OK: [$1] init_returned=true" || { say "EXPECTED FAIL: [$1] init_returned=true"; FAIL=1; }; }
stopif(){ [ $FAIL = 0 ] || { say "STOP: first-trigger check failed; no later case run"; exit 1; }; }
GIB=1073741824

# case 1: first trigger: 1 GiB volume must warn (instrument check)
mnt v1 $GIB
runcase one1g true yes "$M/v1/data"
expect one1g 1; expect_ret one1g
grep -q "^STAGE4 \[one1g\] control request=.*result=returned_directory" "$L/one1g.stage4" && grep -q "^STAGE4 \[one1g\] control request=.*result=threw_FSDiskFullWriteError" "$L/one1g.stage4" && say "EXPECTED OK: [one1g] control: half-of-free returns a directory, twice-free throws FSDiskFullWriteError" || { say "EXPECTED FAIL: [one1g] control"; FAIL=1; }
stopif
umnt v1

# case 2: two 40 GiB volumes: sum 80 GiB, no warn
mnt v40a 40G; mnt v40b 40G
runcase two40 false yes "$M/v40a/data" "$M/v40b/data"
expect two40 0; expect_ret two40
umnt v40a; umnt v40b

# case 3: 1 GiB + 100 GiB
mnt v1 $GIB; mnt v100 100G
runcase small_big false yes "$M/v1/data" "$M/v100/data"
expect small_big 0; expect_ret small_big
# control on the large volume alone
runcase big_only true yes "$M/v100/data"
expect big_only 0; expect_ret big_only
grep -q "^STAGE4 \[big_only\] control request=.*result=returned_directory" "$L/big_only.stage4" && say "EXPECTED OK: [big_only] control: request of half the free space returns a directory" || { say "EXPECTED FAIL: [big_only] control"; FAIL=1; }
umnt v1; umnt v100

# case 4/5: boundary
mnt v639 65433m; runcase b639 false yes "$M/v639/data"; expect b639 1; expect_ret b639; umnt v639
mnt v641 65639m; runcase b641 false yes "$M/v641/data"; expect b641 0; expect_ret b641; umnt v641

# case 6: full volume
mnt v1 $GIB
fallocate -l $GIB "$M/v1/fill" 2>/dev/null || dd if=/dev/zero of="$M/v1/fill" bs=1M 2>/dev/null
say "after fill: avail=$(df -B1 --output=avail "$M/v1" | tail -1)"
runcase full true yes "$M/v1/data"
expect full 1; expect_ret full
umnt v1

# case 7: same yaml minus data_file_directories (default dir <storagedir>/data on local disk)
runcase nodirs false no "$W/storage/data"
expect_ret nodirs
say "(nodirs: local disk avail $(df -B1 --output=avail "$W" | tail -1) bytes; warn_count=$(getn nodirs))"

# Config unchanged across WARN / no-WARN (data_file_directories excluded from the dump)
if cmp -s "$L/one1g.config.txt" "$L/b641.config.txt" && cmp -s "$L/b639.config.txt" "$L/b641.config.txt" && cmp -s "$L/full.config.txt" "$L/b641.config.txt"; then say "EXPECTED OK: Config dump (all fields but data_file_directories) identical for one1g, b639, full (WARN) and b641 (no WARN); two-directory cases differ only by directory count: $(diff "$L/one1g.config.txt" "$L/two40.config.txt" | grep -c "^<") fields"; else say "EXPECTED FAIL: Config dump differs"; diff "$L/one1g.config.txt" "$L/b641.config.txt" | head -5 | tee -a "$SUM"; FAIL=1; fi
say "unit-run $RUN done FAIL=$FAIL"; exit $FAIL
