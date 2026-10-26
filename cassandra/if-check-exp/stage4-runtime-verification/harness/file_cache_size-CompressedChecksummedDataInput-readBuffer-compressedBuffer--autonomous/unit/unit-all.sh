#!/usr/bin/env bash
# usage: unit-all.sh <tree> <outdir>   -- compiles the main class, runs every cell (4 at a time), writes <outdir>/cells/*.log and <outdir>/index.txt
set -u
TREE=$1; OUT=$2; HD=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT/classes $OUT/cells
CP="$TREE/build/classes/main:$TREE/build/test/classes:$(ls $TREE/build/lib/jars/*.jar $TREE/build/test/lib/jars/*.jar | tr '\n' ':')"
javac -d $OUT/classes -cp "$CP" $HD/FcsReadBufferMain.java || exit 1
{
for th in 1 8 64 512; do
  echo "control $th LZ4Compressor 65536 0 0"
  for B in 32768 102400 1048576 6291456; do
    case $B in 32768|102400) n=40;; 1048576) n=8;; *) n=6;; esac
    for R in 1 2 8; do echo "reader $th LZ4Compressor $B $n $R"; done
  done
  for B in 1048576 6291456; do
    case $B in 1048576) n=8;; *) n=6;; esac
    for R in 1 8; do echo "reader $th DeflateCompressor $B $n $R"; done
  done
done
} > $OUT/cells.txt
echo "cells: $(wc -l < $OUT/cells.txt)"
cat $OUT/cells.txt | xargs -P 4 -L 1 bash -c 'bash '"$HD"'/run-cell.sh '"$TREE $OUT"' $0 $1 $2 $3 $4 $5' | tee $OUT/index.txt
