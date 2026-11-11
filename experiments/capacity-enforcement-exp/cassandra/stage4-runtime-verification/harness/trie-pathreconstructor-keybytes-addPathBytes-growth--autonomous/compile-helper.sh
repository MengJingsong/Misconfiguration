#!/bin/bash
# Usage: bash compile-helper.sh <tree> <outdir>: compiles TpHelper into <outdir>/tphelper.jar
set -e
TREE=$1; OUT=$2; HARN=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT/cls
javac -d $OUT/cls $HARN/TpHelper.java
( cd $OUT/cls && jar cf ../tphelper.jar org )
echo built $OUT/tphelper.jar
