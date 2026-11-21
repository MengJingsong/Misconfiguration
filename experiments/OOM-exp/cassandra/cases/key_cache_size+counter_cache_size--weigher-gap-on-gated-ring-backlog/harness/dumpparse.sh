#!/usr/bin/env bash
# R11 (from S2 run-2 dumpparse.sh): reduce an OOM dump to a class histogram on pc96 (x86, idle), not on the m400s.
#   dumpparse.sh <arm> <role> <node>   The dump stays on the node (/mydata/r11/dumps/<arm>-<role>.hprof) for cal1 and
#   T-r1 (design §2.9); for the other arms it is deleted on the node once its histogram is on pc96. pc96's copy is deleted.
A=$1 N=$2 HN=$3; D=/mydata/r11-evidence/dumps; L=/mydata/r11-evidence/runs/$A/$N; mkdir -p $D $L
ssh $HN "ls /mydata/r11/dumps/$A-$N.hprof" >/dev/null 2>&1 || exit 0
rsync -a $HN:/mydata/r11/dumps/$A-$N.hprof $D/ && nice -n 10 timeout 1800 python3 $(dirname $0)/hprofhist.py $D/$A-$N.hprof 40 > $L/dump-hist.txt 2>&1
ok=$?; sz=$(stat -c %s $D/$A-$N.hprof); rm -f $D/$A-$N.hprof
case $A in cal1|T-r1) echo "dump kept at $HN:/mydata/r11/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt;;
  *) if [ $ok = 0 ] && grep -q 'org.apache.cassandra' $L/dump-hist.txt; then ssh $HN "rm -f /mydata/r11/dumps/$A-$N.hprof"; echo "dump ($sz B) parsed and deleted on $HN" >> $L/dump-hist.txt
     else echo "parse failed (rc=$ok); dump left at $HN:/mydata/r11/dumps/$A-$N.hprof ($sz B)" >> $L/dump-hist.txt; fi;;
esac
