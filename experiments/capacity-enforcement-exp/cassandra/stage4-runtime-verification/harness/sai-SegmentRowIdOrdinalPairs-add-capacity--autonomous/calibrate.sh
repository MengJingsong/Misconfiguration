#!/usr/bin/env bash
# Instrument calibration: the same Byteman rules (sr.btm) and helper run around SrMem (no Cassandra node) at N = 1, 1000, 100000 and 10^6.
# Prints K = alloc_ctor(rule) - (16 + 8N), the bytes the rule machinery itself adds between entry and exit. usage: calibrate.sh <tree> <outdir>
# Writes <outdir>/calib.txt ("K <bytes>" per N, and "K_MODE <bytes>"). SrMem must have been compiled by unit-run.sh into <outdir>/../unit/classes.
set -eu
H=$(cd "$(dirname "$0")" && pwd); T=${1:?}; O=${2:?}; mkdir -p "$O/h"
javac -d "$O/h" "$H/SrHelper.java"; jar cf "$O/sr.jar" -C "$O/h" .
CP="$T/build/classes/main:$T/build/lib/jars/*:$T/lib/*"; BM=$T/build/lib/jars/byteman-4.0.20.jar
javac -cp "$CP" -d "$O/classes" "$H/SrMem.java"
: > "$O/calib.txt"
for n in 1 1000 100000 1000000; do
  rm -f "$O/sr-$n.out"
  java -Xmx2g -XX:+UseSerialGC -XX:-DoEscapeAnalysis -ea -Dstage4.sr.out="$O/sr-$n.out" -Xbootclasspath/a:"$O/sr.jar" \
       -javaagent:$BM=script:$H/sr.btm,listener:false -cp "$O/classes:$CP" SrMem pairs $n 0 > "$O/calib-$n.stdout" 2>&1
  # the measured construction is the last line with cap == n
  grep " cap=$n " "$O/sr-$n.out" | tail -1 | awk -v n=$n '{split($6,a,"="); split($3,c,"="); printf "N=%d alloc_ctor=%d K=%d %s\n", n, a[2], a[2]-(16+8*n), $0}' >> "$O/calib.txt"
done
awk '{for(i=1;i<=NF;i++) if($i ~ /^K=/){split($i,a,"="); print a[2]}}' "$O/calib.txt" | sort | uniq -c | sort -rn | head -1 | awk '{print "K_MODE " $2}' >> "$O/calib.txt"
cat "$O/calib.txt"
