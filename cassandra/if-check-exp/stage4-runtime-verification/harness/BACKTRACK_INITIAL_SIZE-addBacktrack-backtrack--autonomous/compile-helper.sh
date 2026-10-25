#!/bin/bash
# Usage: bash compile-helper.sh <tree> <outdir>: compiles BtHelper into <outdir>/bthelper.jar
set -e
TREE=$1; OUT=$2; HARN=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT/cls
javac -d $OUT/cls $HARN/BtHelper.java
( cd $OUT/cls && jar cf ../bthelper.jar org )
echo built $OUT/bthelper.jar
