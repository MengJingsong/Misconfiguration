#!/usr/bin/env bash
# R19 (from R11 dumpparse.sh): reduce an OOM dump to a class histogram on pc96 (x86), not on the m400s.
#   dumpparse.sh <arm> <role> <node>. At most ONE dump is kept on the node (the first counted T dump, arm T1..T9; marker
#   /mydata/r19-evidence/KEPT); every other dump is deleted on the node once its histogram is on pc96. pc96 copy deleted.
A=$1 N=$2 HN=$3; D=/mydata/r19-evidence/dumps; L=/mydata/r19-evidence/runs/$A/$N; mkdir -p $D $L
ssh $HN "ls /mydata/r19/dumps/$A-$N.hprof" >/dev/null 2>&1 || exit 0
rsync -a $HN:/mydata/r19/dumps/$A-$N.hprof $D/ && nice -n 10 timeout 1800 python3 $(dirname $0)/hprofhist.py $D/$A-$N.hprof 40 > $L/dump-hist.txt 2>&1
ok=$?; sz=$(stat -c %s $D/$A-$N.hprof); rm -f $D/$A-$N.hprof
KEEP=0; case $A in T[0-9]*) [ -e /mydata/r19-evidence/KEPT ] || KEEP=1;; esac
if [ $KEEP = 1 ] && [ $ok = 0 ]; then echo "$A-$N" > /mydata/r19-evidence/KEPT; echo "dump kept at $HN:/mydata/r19/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt
elif [ $ok = 0 ] && grep -q 'org.apache.cassandra' $L/dump-hist.txt; then ssh $HN "rm -f /mydata/r19/dumps/$A-$N.hprof"; echo "dump ($sz B) parsed and deleted on $HN" >> $L/dump-hist.txt
else echo "parse failed (rc=$ok); dump left at $HN:/mydata/r19/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt; fi
