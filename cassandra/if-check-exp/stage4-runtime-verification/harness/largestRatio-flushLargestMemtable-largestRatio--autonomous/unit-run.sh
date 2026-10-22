#!/usr/bin/env bash
# Unit tier (B2e, with audit amendments R2-R3) of largestRatio-flushLargestMemtable-largestRatio--autonomous.
# usage (on the run node, call with bash): unit-run.sh <run> orig|first|never|all
#   orig  : ~/cassandra-lrt (unmodified): L=128MiB all four methods (B2e steps 2-3); L=32MiB u3CapSkew,u3CapEven (step 4)
#   first : ~/cassandra-lrt-mut with M-first applied (line 274 -> `largestMemtable == null && ratio > 0f`), rebuilt:
#           u3CapSkew,u3CapEven at L=32 and L=128 (step 5)
#   never : ~/cassandra-lrt-mut reverted, M-never applied (line 251 -> `float largestRatio = Float.MAX_VALUE;`), rebuilt:
#           u3CapSkew at L=32 (step 5)
# Output: ~/stage4-logs/lrt/<run>/unit/ (cmd.log with every command and its output, one dir per JVM run: probe.txt,
# ant.log, TEST-*.xml, test log, gc.log; mutant diffs). The knob line `memtable_heap_space: <L>` is put before the
# `memtable:` block of test/conf/cassandra.yaml (B2b); the yaml is restored from git at the end of each stage.
# Only java processes whose command line contains the clone path are ever killed.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
RUN=${1:?run name}; STAGE=${2:?orig|first|never|all}
ORIG=${LRT_ORIG:-$HOME/cassandra-lrt}; MUT=${LRT_MUT:-$HOME/cassandra-lrt-mut}
L=$HOME/stage4-logs/lrt/$RUN/unit; mkdir -p "$L"; LOG=$L/cmd.log
CLASS=org.apache.cassandra.db.memtable.FlushLargestSelectionTest
SRC=src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
run() { say "+ $*"; ( "$@" ) >> "$LOG" 2>&1; local rc=$?; say "  rc=$rc"; return $rc; }

set_L() {  # clone, MiB
  local c=$1 mib=$2 y=$1/test/conf/cassandra.yaml
  git -C "$c" checkout -- test/conf/cassandra.yaml
  sed -i "/^memtable:/i memtable_heap_space: ${mib}MiB" "$y"
  say "yaml $c: $(grep -n '^memtable_heap_space\|^memtable:\|^memtable_allocation_type' "$y" | tr '\n' ' ')"
  [ "$(grep -c "^memtable_heap_space: ${mib}MiB" "$y")" = 1 ] || { say "FATAL knob line not set"; exit 1; }
}

kill_leftovers() {  # only java processes of this clone
  local c=$1 pids
  pids=$(ps -eo pid,args | awk -v c="$c/" '$2 ~ /java$/ && index($0, c) {print $1}')
  [ -n "$pids" ] && { say "killing leftover java of $c: $pids"; kill $pids; sleep 5; kill -9 $pids 2>/dev/null; }
  return 0
}

one() {  # clone label mutant mib methods [junit timeout ms]
  local c=$1 label=$2 mut=$3 mib=$4 methods=$5 tmo=${6:-1500000} d=$L/$2
  mkdir -p "$d"; : > "$d/probe.txt"
  set_L "$c" "$mib"
  cp "$H/FlushLargestSelectionTest.java" "$c/test/unit/org/apache/cassandra/db/memtable/"
  rm -rf "$c/build/test/cassandra" "$c"/build/test/output/TEST-$CLASS*.xml
  local t0=$(date +%s)
  say "+ [$label] ant testsome $CLASS methods=$methods L=${mib}MiB mutant=$mut (clone $c)"
  ( cd "$c" && timeout 1800 ant testsome -Dtest.name=$CLASS ${methods:+-Dtest.methods=$methods} -Dtest.timeout=$tmo \
      -Dtest.jvm.args="-Dprobe.out=$d/probe.txt -Dprobe.mutant=$mut -Xlog:gc:file=$d/gc.log" ) > "$d/ant.log" 2>&1 < /dev/null
  local rc=$?
  kill_leftovers "$c"
  cp "$c"/build/test/output/TEST-$CLASS*.xml "$d/" 2>/dev/null
  cp "$c"/build/test/logs/_jdk11/TEST-$CLASS*.log "$d/" 2>/dev/null
  say "  [$label] ant rc=$rc $(( $(date +%s) - t0 )) s; $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$d/ant.log"); probe lines $(grep -c '^PROBE' "$d/probe.txt")"
  grep '^PROBE' "$d/probe.txt" | grep -v 'u3-series' | sed "s/^/  [$label] /" | tee -a "$LOG"
}

build() {  # clone label
  say "+ ant build-test in $1"
  ( cd "$1" && ant build-test < /dev/null ) > "$L/build-$2.log" 2>&1
  local rc=$?
  say "  build $2 rc=$rc $(grep -m1 'BUILD' "$L/build-$2.log")"
  [ $rc = 0 ] || { say "FATAL build failed"; exit 1; }
}

say "unit-run $RUN $STAGE host $(hostname -s) java $(java -version 2>&1 | head -1) harness md5 $(md5sum "$H/FlushLargestSelectionTest.java" | cut -c1-12)"
say "free on /: $(df -BG --output=avail / | tail -1)"

if [ "$STAGE" = orig ] || [ "$STAGE" = all ]; then
  say "clone $ORIG $(git -C "$ORIG" describe --tags) $(git -C "$ORIG" rev-parse --short HEAD) diff-of-src: $(git -C "$ORIG" diff --stat -- src | tail -1)"
  [ -z "$(git -C "$ORIG" diff -- src)" ] || { say "FATAL M-orig clone has source changes"; exit 1; }
  one "$ORIG" orig-L128 M-orig 128 ""
  one "$ORIG" orig-L32 M-orig 32 "u3CapSkew,u3CapEven"
  git -C "$ORIG" checkout -- test/conf/cassandra.yaml
fi
if [ "$STAGE" = first ] || [ "$STAGE" = all ]; then
  git -C "$MUT" checkout -- "$SRC"
  sed -i '274s/if (ratio > largestRatio)/if (largestMemtable == null \&\& ratio > 0f)/' "$MUT/$SRC"
  git -C "$MUT" diff -- "$SRC" > "$L/M-first.diff"; cat "$L/M-first.diff" >> "$LOG"
  [ "$(grep -c '^+.*largestMemtable == null && ratio > 0f' "$L/M-first.diff")" = 1 ] || { say "FATAL M-first not applied"; exit 1; }
  build "$MUT" M-first
  one "$MUT" first-L32 M-first 32 "u3CapSkew,u3CapEven"
  one "$MUT" first-L128 M-first 128 "u3CapSkew,u3CapEven"
  git -C "$MUT" checkout -- test/conf/cassandra.yaml
fi
if [ "$STAGE" = never ] || [ "$STAGE" = all ]; then
  git -C "$MUT" checkout -- "$SRC"
  sed -i '251s/float largestRatio = 0f;/float largestRatio = Float.MAX_VALUE;/' "$MUT/$SRC"
  git -C "$MUT" diff -- "$SRC" > "$L/M-never.diff"; cat "$L/M-never.diff" >> "$LOG"
  [ "$(grep -c '^+.*float largestRatio = Float.MAX_VALUE;' "$L/M-never.diff")" = 1 ] || { say "FATAL M-never not applied"; exit 1; }
  build "$MUT" M-never
  # harness fix H2: the M-never test JVM does not exit after its window (attempt 1 waited out the 1500 s junit
  # timeout); its reading is written within ~40 s, so the JVM is given 240 s. The junit timeout error that follows is expected.
  one "$MUT" never-L32 M-never 32 "u3CapSkew" 240000
  git -C "$MUT" checkout -- test/conf/cassandra.yaml
fi
say "leftover java of the clones: $(ps -eo args | awk '$1 ~ /java$/' | grep -c 'cassandra-lrt')"
say "done $STAGE"
