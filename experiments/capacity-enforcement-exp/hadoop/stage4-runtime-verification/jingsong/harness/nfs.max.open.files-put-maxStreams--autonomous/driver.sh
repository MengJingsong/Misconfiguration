#!/usr/bin/env bash
# Detached driver for the cluster tier on pc75: compile, setup, all arms, and ALWAYS teardown.
R=/mydata/jingsong-s4/nfs.max.open.files-put-maxStreams-run1
S=$R/harness/cluster-run.sh
echo "driver start $(date '+%F %T %Z') pid $$"
bash "$S" compile && bash "$S" setup && bash "$S" all
echo "driver arms exit $?"
bash "$S" teardown
echo "DRIVER DONE $(date '+%F %T %Z')"
rm -f /mydata/s4/DRIVER-jingsong-s4-o18.pid
