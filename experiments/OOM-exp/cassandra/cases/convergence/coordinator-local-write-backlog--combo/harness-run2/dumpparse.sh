#!/usr/bin/env bash
# S2 run 2: reduce an OOM dump to a class histogram on pc96 (x86, idle) instead of on the busy m400 nodes.
#   dumpparse.sh <arm> <role> <node>   The dump stays on the node (/mydata/s2r2/dumps/<arm>-<role>.hprof);
#   pc96's temporary copy is deleted after parsing.
A=$1 N=$2 HN=$3; D=/mydata/s2r2/dumps; L=/mydata/s2r2-evidence/runs/$A/$N; mkdir -p $D $L
ssh $HN "ls /mydata/s2r2/dumps/$A-$N.hprof" >/dev/null 2>&1 || exit 0
rsync -a $HN:/mydata/s2r2/dumps/$A-$N.hprof $D/ && nice -n 10 timeout 1200 python3 $(dirname $0)/hprofhist.py $D/$A-$N.hprof 40 > $L/dump-hist.txt 2>&1
echo "dump at $HN:/mydata/s2r2/dumps/$A-$N.hprof ($(stat -c %s $D/$A-$N.hprof) B)" >> $L/dump-hist.txt; rm -f $D/$A-$N.hprof
