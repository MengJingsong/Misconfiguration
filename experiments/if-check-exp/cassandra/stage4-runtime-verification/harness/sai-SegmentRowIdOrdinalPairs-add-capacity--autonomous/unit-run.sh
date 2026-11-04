#!/usr/bin/env bash
# Unit tier driver. usage: bash unit-run.sh <tree> <outdir>    (tree = a copy-source.sh tree that has been built with `ant jar`)
# Compiles SrMem against the tree's build/classes/main and lib jars (nothing is written into the tree), then runs one JVM per (mode, N, rep).
# Matrix = B2b/B2e as amended 2026-10-26. Writes <outdir>/unit.log (all output) and <outdir>/summary.txt (RESULT lines, EXPECTED lines).
set -u
TREE=${1:?}; OUT=${2:?}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT/classes"; LOG=$OUT/unit.log; S=$OUT/summary.txt; : > "$S"; : > "$LOG"
CP="$TREE/build/classes/main:$TREE/build/lib/jars/*:$TREE/lib/*"
javac -cp "$CP" -d "$OUT/classes" "$H/SrMem.java" 2>&1 | tee -a "$LOG" || exit 1
( cd "$H" && md5sum SrMem.java unit-run.sh ) | tee -a "$S"
java -version 2>&1 | head -1 | tee -a "$S"
run() { # run <mode> <N> <rep> <heap> <assert flag>
  local out; out=$(java -Xmx$4 -XX:+UseSerialGC -XX:-DoEscapeAnalysis $5 -cp "$OUT/classes:$CP" SrMem $1 $2 $3 2>&1 | tail -n 6)
  echo "+ java -Xmx$4 $5 SrMem $1 $2 $3" >> "$LOG"; echo "$out" >> "$LOG"
  echo "$out" | grep '^RESULT' | sed "s/^RESULT/RESULT flags=$5 xmx=$4/" | tee -a "$S"
  echo "$out" | grep -v '^RESULT' | head -2 | sed 's/^/  OTHER: /' | tee -a "$S"
}
for rep in 1 2 3; do
  for n in 1 1000 16000 100000 1000000 10000000; do
    run pairs $n $rep 2g -ea; run plain $n $rep 2g -ea
  done
  run pairs 100000000 $rep 6g -ea; run plain 100000000 $rep 6g -ea
done
# optional second sweep: no compressed oops (one rep)
for n in 1000 1000000 10000000; do run pairs $n 1 4g "-ea -XX:-UseCompressedOops"; done
# boundaries (B2e step 5, amended): one rep each
run pairs 1073741822 1 16g -ea; run plain 1073741822 1 16g -ea
run pairs 1073741823 1 2g -ea; run pairs 1073741823 1 2g -da
run pairs 1073741824 1 2g -ea; run pairs 1073741824 1 2g -da
echo "unit-run done $(date -u +%FT%TZ)" | tee -a "$S"
