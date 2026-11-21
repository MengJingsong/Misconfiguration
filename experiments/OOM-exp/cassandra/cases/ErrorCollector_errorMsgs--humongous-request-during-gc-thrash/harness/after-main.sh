#!/usr/bin/env bash
# R15: wait (bounded, 2 h) for the main series, then list-b, list-c, and list-d (diagnostic, R15_DIAG=1), in this ssh-less session.
W=/mydata/s4/r15-w5
for i in $(seq 1 720); do grep -q "SERIES DONE" $W/runs/series-list-main.txt.log 2>/dev/null && break; sleep 10; done
bash $W/harness/series.sh $W/harness/list-b.txt
bash $W/harness/series.sh $W/harness/list-c.txt
R15_DIAG=1 bash $W/harness/series.sh $W/harness/list-d.txt
