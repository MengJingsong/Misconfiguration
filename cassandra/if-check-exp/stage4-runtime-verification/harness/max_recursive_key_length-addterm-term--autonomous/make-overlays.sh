#!/usr/bin/env bash
# usage: make-overlays.sh <copy dir>   builds <copy>/build/overlay-{instr,z0,z1,zi0}: a recompiled TrieMemoryIndex.class from a patched copy of the source
# (never written into the repository or the copy's src/). instr: ROUTE_REC/ROUTE_APPLY counters, constant 128; z0: constant 0; z1: constant 100000; zi0: counters and constant 0.
set -euo pipefail
C=${1:?copy dir}; SRC=$C/src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
mk() { # name constant counters(0|1)
  local d=$C/build/overlay-$1 w=$C/build/overlay-src-$1/org/apache/cassandra/index/sai/memory
  rm -rf "$d" "$C/build/overlay-src-$1"; mkdir -p "$d" "$w"
  python3 - "$SRC" "$w/TrieMemoryIndex.java" "$2" "$3" <<'PY'
import sys
src, dst, const, counters = sys.argv[1:5]
t = open(src).read()
a = "private static final int MAX_RECURSIVE_KEY_LENGTH = 128;"
assert a in t
t = t.replace(a, "private static final int MAX_RECURSIVE_KEY_LENGTH = %s;" % const)
if counters == "1":
    t = t.replace("    private static final int MINIMUM_PRIORITY_QUEUE_SIZE = 128;",
                  "    private static final int MINIMUM_PRIORITY_QUEUE_SIZE = 128;\n    public static final java.util.concurrent.atomic.AtomicLong ROUTE_REC = new java.util.concurrent.atomic.AtomicLong();\n    public static final java.util.concurrent.atomic.AtomicLong ROUTE_APPLY = new java.util.concurrent.atomic.AtomicLong();")
    b1 = "data.putRecursive(comparableBytes, primaryKey, primaryKeysReducer);"
    b2 = "data.apply(Trie.singleton(comparableBytes, primaryKey), primaryKeysReducer);"
    assert b1 in t and b2 in t
    t = t.replace(b1, "ROUTE_REC.incrementAndGet(); " + b1).replace(b2, "ROUTE_APPLY.incrementAndGet(); " + b2)
open(dst, "w").write(t)
PY
  javac -nowarn -cp "$CP" -d "$d" "$w/TrieMemoryIndex.java" 2>&1 | grep -v '^Note:' || true
  echo "overlay $1: constant=$2 counters=$3 -> $(ls $d/org/apache/cassandra/index/sai/memory | tr '\n' ' ')"
}
mk instr 128 1
mk z0 0 0
mk z1 100000 0
mk zi0 0 1
