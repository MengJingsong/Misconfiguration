#!/usr/bin/env bash
# o116 unit tier: B2e as written (S4-A1 paths). Every command echoed (set -x).
set -x
W=/mydata/jingsong-cass-s4/o116; SRC=$W/src; RUN=$W/run
date -u +%FT%TZ; date +%s%3N; uptime
cd $SRC
run() {  # $1=name, $2=extra -D args
  date -u +%FT%TZ
  rm -rf $RUN/u/$1; mkdir -p $RUN/u/$1/probe_ks/t
  ant testsome -Dno-build-test=true -Dtest.timeout=1800000 \
      -Dtest.name=org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest \
      -Dtest.jvm.args="-Dprobe.out=$RUN/u/$1/probe_ks/t $2" > $RUN/u/$1.ant.log 2>&1 </dev/null
  echo "ant exit=$?"; grep -E 'Tests run|BUILD' $RUN/u/$1.ant.log
  grep -ho 'PROBE .*' build/test/output/TEST-org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest.* $RUN/u/$1.ant.log | sort -u > $RUN/u/$1.probe.txt
  cp build/test/output/TEST-org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest*.xml $RUN/u/$1.test.xml 2>/dev/null
  rm -f build/test/output/TEST-org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest*
  du -sb $RUN/u/$1; rm -rf $RUN/u/$1                # keep the probe text, drop the SSTables
  grep -cE 'PROBE sync=' $RUN/u/$1.probe.txt; grep -E 'PROBE (writer|syncs|dataFiles)' $RUN/u/$1.probe.txt
}
for x in ${UNITS:-U1 U4 U16 U64 Udef U0 Uinf S16 S64 Ubig Udel}; do
  case $x in
    U1)   run U1   "-Dprobe.mib=1" ;;
    U4)   run U4   "-Dprobe.mib=4" ;;
    U16)  run U16  "-Dprobe.mib=16" ;;
    U64)  run U64  "-Dprobe.mib=64" ;;
    Udef) run Udef "" ;;
    U0)   run U0   "-Dprobe.mib=0" ;;
    Uinf) run Uinf "-Dprobe.mib=1024" ;;
    S16)  run S16  "-Dprobe.mib=16 -Dprobe.mode=sorted" ;;
    S64)  run S64  "-Dprobe.mib=64 -Dprobe.mode=sorted" ;;
    Ubig) run Ubig "-Dprobe.mib=1 -Dprobe.value=3145728 -Dprobe.rpp=1 -Dprobe.rows=5" ;;
    Udel) run Udel "-Dprobe.mib=1 -Dprobe.mode=delete -Dprobe.rows=500000" ;;
    CHK)  run CHK  "-Dprobe.mib=1 -Dprobe.rows=4096" ;;   # instrument check only
  esac
done
ps -eo pid,cmd | grep '[M]axSSTableSizeProbeTest' || echo "no probe JVM left"
date -u +%FT%TZ; echo UNIT-DONE
