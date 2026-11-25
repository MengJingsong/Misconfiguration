#!/usr/bin/env bash
# o116, 2026-11-25, ms0640: the node commands this session ran around setup.sh / unit-all.sh / cluster-all.sh (record, run step by step).
# lock (acquired on the first try, 10:00:04 MST)
ssh ms0640 'mkdir /mydata/s4/NODE-LOCK && echo "jingsong-c116-stage4 $(date)" > /mydata/s4/NODE-LOCK/owner'
# stage the harness and set up (no /tmp staging; S4-A4(a))
ssh ms0640 'rm -rf /mydata/jingsong-cass-s4/o116 /mydata/jingsong-cass-s4/o116-harness.new; mkdir -p /mydata/jingsong-cass-s4/o116-harness.new'
scp MaxSSTableSizeProbeTest.java MaxSSTableSizeProbeTest.filed.java BulkProbe.java setup.sh unit-all.sh cluster-all.sh analyze.py md5.txt ms0640:/mydata/jingsong-cass-s4/o116-harness.new/
ssh ms0640 'bash -s' < setup.sh > ../run1/setup.log 2>&1
# instrument check
ssh ms0640 'UNITS=CHK bash /mydata/jingsong-cass-s4/o116/harness/unit-all.sh' > ../run1/unit-CHK-driver.log 2>&1
# unit tier, detached (PID 732007 recorded in /mydata/s4/DRIVER-jingsong-c116.pid)
ssh ms0640 'cd /mydata/jingsong-cass-s4/o116 && rm -f run/u/CHK.* && setsid nohup bash harness/unit-all.sh > logs/unit-run.log 2>&1 < /dev/null &'
# cluster tier, detached (PID 733296 recorded)
ssh -n ms0640 'cd /mydata/jingsong-cass-s4/o116 && (setsid bash harness/cluster-all.sh > logs/cluster-run.log 2>&1 < /dev/null & echo $! > /mydata/s4/DRIVER-jingsong-c116.pid)'
# analysis (local)
python3 -I analyze.py ../run1/unit ../run1/cluster > ../run1/analysis/analyze-all.out
# cleanup and release (10:16:43 MST)
ssh -n ms0640 'W=/mydata/jingsong-cass-s4/o116; rm -rf $W/src $W/run/p/out-* $W/run/node $W/run/conf $W/run/u/*/; rm -f $W/run/p/BulkProbe.class'
ssh -n ms0640 'ps -u $(id -un) -o pid=,args= | awk "/java|ant|BulkProbe|CassandraDaemon|cluster-all|unit-all|MaxSSTable/ && !/awk/"'
ssh -n ms0640 'rm -f /mydata/s4/DRIVER-jingsong-c116.pid; rm -rf /mydata/s4/NODE-LOCK'
