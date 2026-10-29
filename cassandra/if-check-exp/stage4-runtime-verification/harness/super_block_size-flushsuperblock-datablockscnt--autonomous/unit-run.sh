#!/usr/bin/env bash
# usage: unit-run.sh <label> <ovdir|pristine> <n> <SPARSE|PREFIX> <xmx> [extra java args]   (B2e). One JVM, one build of one index.
# ovdir is a directory under $OV (ov16p, ov64, ...) placed ahead of the build on the class path; "pristine" uses the run copy's build only.
# Output: $OUT/<label>.out (PROBE/TAIL/RESULT lines), $OUT/<label>.log (all stdout, with SBFLUSH lines of the p overlays).
set -uo pipefail
label=$1; ov=$2; n=$3; mode=$4; xmx=$5; shift 5
HARN=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/s4-b34/c}; OV=${OV:-$HOME/s4-b34/ov}; OUT=${OUT:-$HOME/stage4-logs/b34/superblock/run1/unit}; mkdir -p "$OUT" "$OUT/cls" $HOME/s4-b34/tmp
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
[ -f "$OUT/cls/org/apache/cassandra/index/sasi/disk/SuperBlockProbeTest.class" ] || javac -nowarn -d "$OUT/cls" -cp "$CP" "$HARN/SuperBlockProbeTest.java" || exit 1
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
PRE=""; [ "$ov" != pristine ] && PRE="$OV/$ov:"
SB=(); case "$ov" in *p) SB=(-Dsb.log=1);; esac
rm -f "$OUT/$label.out"
echo "== $label ov=$ov n=$n mode=$mode xmx=$xmx $(date -u +%FT%TZ)" > "$OUT/$label.log"
java @"$OUT/jvm11-opens.args" -Xmx$xmx -XX:+UseSerialGC "${SB[@]}" "$@" -Dprobe.n=$n -Dprobe.mode=$mode -Dprobe.label=$label -Dprobe.out="$OUT/$label.out" -Dprobe.tmp=$HOME/s4-b34/tmp \
  -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/s4-b34/tmp/storage \
  -cp "${PRE}$OUT/cls:$CP" org.junit.runner.JUnitCore org.apache.cassandra.index.sasi.disk.SuperBlockProbeTest >> "$OUT/$label.log" 2>&1
echo "== exit $? $(date -u +%FT%TZ)" >> "$OUT/$label.log"
grep -h "^RESULT" "$OUT/$label.out" 2>/dev/null || { echo "$label: no RESULT"; tail -5 "$OUT/$label.log"; }
