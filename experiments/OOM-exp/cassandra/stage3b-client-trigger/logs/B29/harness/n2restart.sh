#!/usr/bin/env bash
# 3-b confirm B29: divA fix-up (2026-11-24 23:30 EST). truncatehints deletes only closed hint files; the writer for a down node
# stays open (HintsDispatchTrigger closes it only when the node is live), so node 2 is restarted (drain closes the writer), then
# truncatehints, then node 2's auth read CL is set again (JMX), then the attacker's event monitor is restarted.
cd /mydata/s4/3b-B29; H=harness; V="bash $H/ctl.sh"; D=ev/divA
cp events.log $D/events-1.log 2>/dev/null
echo "[$(TZ=America/New_York date +%T)] operator: node 2 restart" | tee $D/n2-restart.txt
$V stopn LOAD 2 | tee -a $D/n2-restart.txt; ls -la n2/hints | tee -a $D/n2-restart.txt
$V start LOAD-n2b 2 8G | tee -a $D/n2-restart.txt; $V ready LOAD-n2b 2 | tee -a $D/n2-restart.txt
echo "listpendinghints: $($V nt 2 listpendinghints)" | tee -a $D/n2-restart.txt; ls -la n2/hints | tee -a $D/n2-restart.txt
$V nt 2 truncatehints; sleep 3; echo "after truncatehints:" | tee -a $D/n2-restart.txt; ls -la n2/hints | tee -a $D/n2-restart.txt
echo "listpendinghints: $($V nt 2 listpendinghints)" | tee -a $D/n2-restart.txt
java -cp cls AuthJmx 7299 LOCAL_ONE 2>&1 | tee -a $D/authjmx-n2.txt
rm -f events.stop; ( setsid nohup python3 $H/events.py 127.0.0.2 attacker att-pw 14400 /mydata/s4/3b-B29/events.stop > events.log 2>&1 < /dev/null & ); sleep 3; cat events.log
