#!/usr/bin/env bash
# Record of the one-line commands run from the session node for order 14 on pc82 (2026-11-25, MST node clock).
# Not meant to be run as one script; each block was run by hand in this order.
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration

# 10:00:56 lock
ssh pc82 'mkdir /mydata/s4/NODE-LOCK && echo "jingsong-h14-stage4 $(date)" > /mydata/s4/NODE-LOCK/owner'
# 10:01 node check: hostname, built dist, rpcbind/nfs-server state, mounts, ports, processes (results §2)
# 10:01 run folder + source copy
ssh pc82 "mkdir -p $R/logs $R/harness && $REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh $R/src > $R/logs/copy-source.log 2>&1"
# 10:05 harness to node; unit tier (attempt 1 failed at testCompile; attempt 2 at 10:05:59 after the A2 correction)
scp ~/writeup-hadoop/out/o14/harness/{TestDumpWaterMark.java,unit-run.sh,cluster-run.sh,ooo_write.py,analyze.py,check-unit.py} pc82:$R/harness/
ssh pc82 "cd $R && setsid nohup bash $R/harness/unit-run.sh > $R/logs/unit-driver.out 2>&1 < /dev/null & echo \$! > /mydata/s4/DRIVER-jingsong-h14.pid"
# 10:06:50 cluster tier (jars, setup, arms A B Aprime C D, teardown on exit)
ssh pc82 "cd $R && setsid nohup bash $R/harness/cluster-run.sh all > $R/logs/cluster-driver.out 2>&1 < /dev/null & echo \$! > /mydata/s4/DRIVER-jingsong-h14.pid"
# local analysis (session node)
python3 -I check-unit.py run1/unit/readings.csv
python3 -I analyze.py run1/cluster-full
# 10:22 leftover soft mount from arm D (runbook defect 2)
ssh pc82 'sudo umount -f -l /mnt/hdfs-nfs-jason92; sudo rmdir /mnt/hdfs-nfs-jason92'
# 10:24 bulk delete, gzip large logs, driver pid file
ssh pc82 "cd $R && rm -rf hadoop src nn dn tmp dump pids && find logs -type f \( -name '*.log' -o -name '*.out' -o -name '*.out.[0-9]*' -o -name 'jstat.txt' \) -size +200k -exec gzip -9 {} + ; rm -f /mydata/s4/DRIVER-jingsong-h14.pid"
# end: release lock
ssh pc82 'rm -rf /mydata/s4/NODE-LOCK'
