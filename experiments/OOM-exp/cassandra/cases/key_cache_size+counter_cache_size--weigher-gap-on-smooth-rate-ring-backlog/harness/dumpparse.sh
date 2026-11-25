#!/usr/bin/env bash
# R25 (copied from R19, paths /mydata/r25, R1 on ms0640; 2026-11-24). R19 (from R11 dumpparse.sh): reduce an OOM dump to a class histogram on the controller (node0 controller), not on the m400s.
#   dumpparse.sh <arm> <role> <node>. At most ONE dump is kept on the node (the first counted T dump, arm T1..T9; marker
#   /mydata/r25-evidence/KEPT); every other dump is deleted on the node once its histogram is on the controller. controller copy deleted.
A=$1 N=$2 HN=$3; D=/mydata/r25-evidence/dumps; L=/mydata/r25-evidence/runs/$A/$N; mkdir -p $D $L
ssh $HN "ls /mydata/r25/dumps/$A-$N.hprof" >/dev/null 2>&1 || exit 0
rsync -a $HN:/mydata/r25/dumps/$A-$N.hprof $D/ && nice -n 10 timeout 1800 python3 $(dirname $0)/hprofhist.py $D/$A-$N.hprof 40 > $L/dump-hist.txt 2>&1
ok=$?; sz=$(stat -c %s $D/$A-$N.hprof); rm -f $D/$A-$N.hprof
KEEP=0; case $A in T[0-9]*) [ -e /mydata/r25-evidence/KEPT ] || KEEP=1;; esac
if [ $KEEP = 1 ] && [ $ok = 0 ]; then echo "$A-$N" > /mydata/r25-evidence/KEPT; echo "dump kept at $HN:/mydata/r25/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt
elif [ $ok = 0 ] && grep -q 'org.apache.cassandra' $L/dump-hist.txt; then ssh $HN "rm -f /mydata/r25/dumps/$A-$N.hprof"; echo "dump ($sz B) parsed and deleted on $HN" >> $L/dump-hist.txt
else echo "parse failed (rc=$ok); dump left at $HN:/mydata/r25/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt; fi
