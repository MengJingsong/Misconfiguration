#!/usr/bin/env bash
# Step 4 calibration (not readings), 2048M: probe x3, first-trigger checks, shakedown flood zero 4 256 20.
#   calib.sh  (output dir /mydata/s4/B19/runs/calib)
set -uo pipefail
H=/mydata/s4/B19/h; ROOT=/mydata/s4/B19; NODE=$ROOT/node; R=$ROOT/runs/calib
rm -rf $R; mkdir -p $R
"$H/ctl.sh" gen > $R/ctl.log 2>&1 || exit 1
XMX=2048M DUMP=1 "$H/ctl.sh" start >> $R/ctl.log 2>&1
for _ in $(seq 90); do grep -q "Starting listening for CQL clients" $NODE/logs/system.log 2>/dev/null && break; sleep 2; done
VPID=$("$H/ctl.sh" pid)
taskset -c 6-7 jcmd $VPID VM.flags 2>/dev/null | tr ' ' '\n' | grep -E "MaxDirectMemorySize|MaxHeapSize|UseG1GC|G1HeapRegionSize" > $R/V-flags.txt
tr '\0' '\n' < /proc/$VPID/cmdline > $R/V-cmdline.txt
for i in 1 2 3; do "$H/cli.sh" probe; done > $R/probe.log 2>&1
echo "== zero 1 1 5" > $R/trigger.log; "$H/cli.sh" flood zero 1 1 5 >> $R/trigger.log 2>&1
echo "== rand 1 1 5" >> $R/trigger.log; "$H/cli.sh" flood rand 1 1 5 >> $R/trigger.log 2>&1
echo "== bogus 67108864" >> $R/trigger.log; "$H/cli.sh" flood "bogus 67108864" >> $R/trigger.log 2>&1
echo "alive_after_bogus=$(kill -0 $VPID 2>/dev/null && echo yes || echo no)" >> $R/trigger.log
taskset -c 6-7 java -cp /mydata/s4/B19/cls B19Sample 7319 500 "$R" > "$R/sampler.err" 2>&1 & SMP=$!
sleep 3
echo "$(date +%s%3N) flood start" > $R/args.txt
timeout 200 "$H/cli.sh" flood zero 4 256 20 > $R/client.log 2>&1
echo "$(date +%s%3N) flood end" >> $R/args.txt
sleep 5; kill $SMP
echo "alive_after_shakedown=$(kill -0 $VPID 2>/dev/null && echo yes || echo no)" >> $R/trigger.log
for _ in $(seq 60); do kill -0 $VPID 2>/dev/null || break; ls $NODE/dumps/*.hprof >/dev/null 2>&1 || break; sleep 2; done
mkdir -p $R/V-logs; cp -p $NODE/logs/system.log $NODE/logs/gc.log* $NODE/logs/stdout.log $R/V-logs/ 2>/dev/null
"$H/ctl.sh" stop >> $R/ctl.log 2>&1
ls -la $NODE/dumps/ >> $R/trigger.log; rm -rf $NODE/dumps/*.hprof
python3 -I $H/b19peaks.py $R > $R/peaks.txt 2>&1
echo CALIB_DONE
